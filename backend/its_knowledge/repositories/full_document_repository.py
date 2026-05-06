# backend/its_knowledge/repositories/full_document_repository.py
import json
from typing import List, Optional, Tuple, Dict, Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.its_knowledge.config.settings import settings
from langchain_openai.embeddings import OpenAIEmbeddings
import logging

logger = logging.getLogger(__name__)


class FullDocumentRepository:
    """
    全文档集合仓储
    存储文档完整内容，用于标题检索时快速获取
    """

    def __init__(self):
        self.embedding = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.API_KEY,
            openai_api_base=settings.BASE_URL,
        )
        self.collection = Chroma(
            persist_directory=settings.VECTOR_STORE_PATH,
            collection_name=settings.FULL_DOC_COLLECTION,
            embedding_function=self.embedding
        )

    def add_document(self, content: str, title: str, path: str, title_vector: List[float]) -> Optional[str]:
        doc = Document(
            page_content=content,
            metadata={
                "title": title,
                "path": path,
                "title_vector_json": json.dumps(title_vector)
            }
        )
        ids = self.collection.add_documents([doc])
        logger.info(f"全文档已存储: {title}")
        return ids[0] if ids else None

    def get_by_title(self, title: str) -> Optional[Document]:
        results = self.collection.get(where={"title": title})
        if results and results.get("documents"):
            return Document(
                page_content=results["documents"][0],
                metadata=results["metadatas"][0]
            )
        return None

    def get_by_titles(self, titles: List[str]) -> List[Document]:
        documents = []
        for title in titles:
            doc = self.get_by_title(title)
            if doc:
                documents.append(doc)
        return documents

    def delete_by_title(self, title: str) -> bool:
        doc = self.get_by_title(title)
        if not doc:
            return False
        try:
            results = self.collection.get(where={"title": title})
            if results and results.get("ids"):
                self.collection.delete(ids=results["ids"])
                logger.info(f"全文档已删除: {title}")
                return True
        except Exception as e:
            logger.error(f"删除全文档失败: {title}, 原因: {e}")
        return False

    def count(self) -> int:
        return self.collection._collection.count()

    def list_all(self, offset: int = 0, limit: int = 20, search: str = None) -> Tuple[List[Dict[str, Any]], int]:
        """分页列出文档，支持按标题搜索"""
        results = self.collection.get(include=["metadatas"])
        if not results or not results.get('metadatas'):
            return [], 0

        docs = []
        for i, meta in enumerate(results['metadatas']):
            title = meta.get('title', '')
            if search and search.lower() not in title.lower():
                continue
            docs.append({
                'id': results['ids'][i] if results.get('ids') else str(i),
                'title': title,
                'path': meta.get('path', ''),
            })
        total = len(docs)
        return docs[offset:offset + limit], total

    def get_preview(self, title: str, max_chars: int = 1000) -> Optional[str]:
        """获取文档内容预览"""
        doc = self.get_by_title(title)
        if doc:
            return doc.page_content[:max_chars]
        return None