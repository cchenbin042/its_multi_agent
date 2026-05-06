import os
import json
import hashlib
from typing import List

from langchain_community.vectorstores.utils import filter_complex_metadata
from backend.its_knowledge.repositories.vector_store_repository import VectorStoreRepository
from backend.its_knowledge.repositories.full_document_repository import FullDocumentRepository
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_core.documents import Document
import logging

from backend.its_knowledge.services.ingestion.document_loader_factory import DocumentLoaderFactory
from backend.its_knowledge.utils.document_converter import DocumentConverter
from backend.its_knowledge.config.settings import settings

logger = logging.getLogger(__name__)


class IngestionProcessor:
    """
    文档处理类，负责文档的读取、分块、向量化等
    """
    def __init__(self):
        self.vector_store = VectorStoreRepository()
        self.full_doc_store = FullDocumentRepository()
        # 实例化文档切分器【递归】
        # 修复：使用 settings 配置而非硬编码
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,  # 使用配置值
            chunk_overlap=settings.CHUNK_OVERLAP,  # 使用配置值
            # 自定义切分策略，优先按照标题【\n##】切分，如果chunk还是很大，在按照加粗去切分【\n**】，默认的切分策略是按照【\n\n】、\n、空格、空字符串
            separators=[
                "\n##",
                "\n**",
                "\n\n",
                "\n",
                " ",
                ""
            ]
        )

    def _compute_content_hash(self, content: str) -> str:
        """
        P1优化：计算内容的 MD5 hash，用于去重
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _check_duplicate(self, content_hash: str) -> bool:
        """
        P1优化：检查向量库中是否已存在相同 hash 的文档
        Returns:
            bool: True 表示已存在（重复），False 表示不存在
        """
        try:
            results = self.vector_store.vector_database._collection.get(
                where={"content_hash": content_hash},
                limit=1
            )
            return bool(results and results.get('ids'))
        except Exception as e:
            logger.warning(f"检查重复文档失败: {e}")
            return False

    def _delete_by_content_hash(self, content_hash: str) -> int:
        """
        P1优化：删除向量库中相同 hash 的旧文档（用于更新）
        Returns:
            int: 删除的文档数
        """
        try:
            results = self.vector_store.vector_database._collection.get(
                where={"content_hash": content_hash}
            )
            if results and results.get('ids'):
                self.vector_store.vector_database._collection.delete(ids=results['ids'])
                logger.info(f"已删除旧文档: content_hash={content_hash}, 数量={len(results['ids'])}")
                return len(results['ids'])
        except Exception as e:
            logger.warning(f"删除旧文档失败: {e}")
        return 0

    def ingest_file(self, file_path: str, skip_duplicate: bool = True) -> int:
        """
        文档入库（支持语义分块、标题向量预计算、P1优化：去重/更新机制）
        Args:
            file_path: 文件路径
            skip_duplicate: True 表示跳过重复文档，False 表示更新（删除旧文档再添加）

        Returns:
            int: 保存成功的文档数，0 表示跳过重复或失败
        """
        filename = os.path.basename(file_path)

        # 1. 验证文件格式
        if not DocumentLoaderFactory.is_supported(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            raise ValueError(f"不支持的文件格式: {ext}")

        # 2. 使用工厂获取对应 Loader 并加载文件
        try:
            loader = DocumentLoaderFactory.get_loader(file_path)
            documents = loader.load()
        except Exception as e:
            logger.error(f"文件加载失败: {file_path}, 原因: {str(e)}")
            raise

        # 3. 获取文件扩展名和标题
        file_ext = os.path.splitext(file_path)[1].lower()
        title = DocumentConverter.extract_title(file_path)

        # 4. 转换为 Markdown 格式
        markdown_content = DocumentConverter.to_markdown(documents, file_ext)

        # P1优化：计算内容 hash，检查重复
        content_hash = self._compute_content_hash(markdown_content)
        if self._check_duplicate(content_hash):
            if skip_duplicate:
                logger.info(f"文档已存在，跳过: {title} (hash={content_hash})")
                return 0
            else:
                # 更新模式：删除旧文档
                deleted_count = self._delete_by_content_hash(content_hash)
                logger.info(f"更新文档: {title}, 删除旧文档 {deleted_count} 条")

        # 5. 计算标题向量
        title_vector = self.vector_store.embedding.embed_query(title)

        # 6. 存储全文档（先删除旧的全文档记录）
        self.full_doc_store.delete_by_title(title)
        self.full_doc_store.add_document(
            content=markdown_content,
            title=title,
            path=file_path,
            title_vector=title_vector
        )
        logger.info(f"全文档已存储: {title}")

        # 7. 使用语义分块
        final_chunks = self.split_by_semantic(markdown_content, filename)
        for chunk in final_chunks:
            chunk.metadata['title'] = title
            # P1优化：在 metadata 中存储 content_hash
            chunk.metadata['content_hash'] = content_hash

        # 8. 过滤复杂元数据
        clean_chunks = filter_complex_metadata(final_chunks)

        # 9. 无效性检查
        valid_chunks = [d for d in clean_chunks if d.page_content.strip()]

        if not valid_chunks:
            logger.error("切分后的文档块没有任何的内容")
            return 0

        # 10. 注入标题向量（使用 JSON 字符串，Chroma 不支持 bytes）
        title_vector_json = json.dumps(title_vector)
        for chunk in valid_chunks:
            chunk.metadata['title_vector_json'] = title_vector_json

        # 11. 存储到向量数据库
        return self.vector_store.add_documents(valid_chunks)

    def split_by_semantic(self, content: str, filename: str) -> List[Document]:
        """
        按Markdown标题层级语义分块
        Args:
            content: Markdown文档内容
            filename: 文件名

        Returns:
            List[Document]: 切分后的文档块列表
        """
        headers_to_split_on = [
            ("##", "section"),
            ("###", "subsection"),
        ]

        md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False
        )

        try:
            chunks = md_splitter.split_text(content)
        except Exception:
            return self._fallback_split(content, filename)

        final_chunks = []
        for chunk in chunks:
            section_path = chunk.metadata.get('section', '')
            subsection = chunk.metadata.get('subsection', '')
            if subsection:
                section_path = f"{section_path} > {subsection}"

            if len(chunk.page_content) > settings.CHUNK_SIZE:
                sub_chunks = self.text_splitter.split_text(chunk.page_content)
                for sub in sub_chunks:
                    doc = Document(
                        page_content=f"文档来源：{filename}\n章节路径：{section_path}\n{sub}",
                        metadata={'source': filename, 'title': filename, 'section_path': section_path}
                    )
                    final_chunks.append(doc)
            else:
                chunk.page_content = f"文档来源：{filename}\n章节路径：{section_path}\n{chunk.page_content}"
                chunk.metadata.update({'source': filename, 'title': filename, 'section_path': section_path})
                final_chunks.append(chunk)

        return final_chunks

    def _fallback_split(self, content: str, filename: str) -> List[Document]:
        """
        兜底切分方法，当语义分块失败时使用
        Args:
            content: 文档内容
            filename: 文件名

        Returns:
            List[Document]: 切分后的文档块列表
        """
        chunks = self.text_splitter.split_text(content)
        return [
            Document(page_content=f"文档来源：{filename}\n{chunk}", metadata={'source': filename, 'title': filename})
            for chunk in chunks
        ]
