from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.its_knowledge.config.settings import settings
from langchain_openai.embeddings import OpenAIEmbeddings
import logging
logger = logging.getLogger(__name__)

class VectorStoreRepository:
    """
    对向量数据库做场景读写
    """
    def __init__(self):
        """
        初始化向量数据库
        """
        self.embedding = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            openai_api_key=settings.API_KEY,
            openai_api_base=settings.BASE_URL,
        )
        self.vector_database = Chroma(
            persist_directory=settings.VECTOR_STORE_PATH, # 广义上的库
            collection_name="its-knowledge",
            embedding_function=self.embedding
        )

    def add_documents(self, documents: list, batch_size: int = 16) -> int:
        """
        将切分之后的文档批量添加到向量数据库中
        Args:
            documents: 切分之后的文档块
            batch_size:批次大小

        Returns:
            int: 成功添加的文档数量

        """
        # 1、获取文档块的总数量
        total_documents_chunk = len(documents)
        # 2、分批次保存
        # 场景 [1,2,3,4,5] batch_size=2; 遍历3次，第一次取[1,2]；第二次取【3，4】；第三次取【5】
        # 定义添加成功的标志位
        documents_chunks_added = 0
        try:
            for i in range(0, total_documents_chunk, batch_size):
                # 获取当前批次的文档块
                chunk = documents[i:i + batch_size]
                # 添加当前批次的文档块
                self.vector_database.add_documents(chunk)
                documents_chunks_added += len(chunk)
                logger.info(f"Added {len(chunk)} documents chunks to the vector database")
            return documents_chunks_added
        except Exception as e:
            logger.error(f"Error adding documents chunks to the vector database: {e}")
            raise e

    def embedd_document(self,text:str) ->List[float]:
        """

        Args:
            text: 输入的文本

        Returns:
            List[float]: 文本的向量表示

        """
        return self.embedding.embed_query(text)

    def embedd_documents(self,texts:list[str],batch_size:int=32) ->List[List[float]]:
        """
        将文本列表转换为向量列表（分批处理，避免 API 批次限制）
        Args:
            texts: 文本列表
            batch_size: 批次大小，默认32（SiliconFlow API限制为64）

        Returns:
            List[List[float]]: 向量列表，每个向量表示一个文本

        """
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.embedding.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)
        return all_embeddings

    def search_similarity_with_score(self, user_question: str, k: int = 5, precomputed_vector: List[float] = None) -> list[tuple[Document, float]]:
        """
        相似性检索带分数
        分数：（chroma向量数据库）返回的是l2距离，越小越相似，越接近0越相似，不是余弦相似度，也不是cosine距离
        Args:
            user_question: 用户问题
            k: 返回数量
            precomputed_vector: 预计算的向量（可选，避免重复API调用）

        Returns:
            list[tuple[Document, float]]: 相似性检索结果，返回一个文档列表

        """
        if precomputed_vector:
            # 使用预计算向量直接查询底层 collection
            results = self.vector_database._collection.query(
                query_embeddings=[precomputed_vector],
                n_results=k,
                include=["documents", "metadatas", "distances"]
            )
            # 转换为标准格式
            documents = []
            if results and results.get('documents') and results['documents'][0]:
                for i, (doc_content, meta, distance) in enumerate(zip(
                    results['documents'][0],
                    results['metadatas'][0] if results.get('metadatas') else [],
                    results['distances'][0] if results.get('distances') else []
                )):
                    doc = Document(page_content=doc_content, metadata=meta)
                    documents.append((doc, distance))
            return documents
        else:
            result = self.vector_database.similarity_search_with_score(user_question, k=k)
            return result

