# backend/its_knowledge/services/reranker_service.py
import logging
import requests
from typing import List

from langchain_core.documents import Document

from backend.its_knowledge.config.settings import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """
    Cross-Encoder 精排服务

    调用外部 rerank API（如 SiliconFlow）对候选文档进行深度语义匹配排序
    """

    def __init__(self):
        self.api_url = settings.RERANK_API_URL
        self.api_key = settings.API_KEY
        self.model = settings.RERANK_MODEL

    def rerank(
        self,
        query: str,
        documents: List[Document],
        top_k: int = 20
    ) -> List[Document]:
        """
        对文档列表进行重排序

        Args:
            query: 用户问题（使用原始问题，非扩展查询）
            documents: 候选文档列表
            top_k: 返回数量

        Returns:
            重排序后的文档列表（按相关性降序）
        """
        if not documents:
            return []

        if len(documents) <= top_k:
            return self._call_rerank_api(query, documents)

        return self._call_rerank_api(query, documents, top_k)

    def _call_rerank_api(
        self,
        query: str,
        documents: List[Document],
        top_k: int = None
    ) -> List[Document]:
        """调用 rerank API"""
        if not self.api_url:
            logger.warning("Rerank API URL 未配置，跳过精排")
            return self._fallback_sort(documents, top_k)

        texts = [doc.page_content for doc in documents]

        payload = {
            "model": self.model,
            "query": query,
            "documents": texts,
            "top_n": top_k or len(texts)
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            results = response.json().get("results", [])

            reranked_docs = []
            for item in results:
                idx = item.get("index", 0)
                score = item.get("relevance_score", 0)

                if idx < len(documents):
                    doc = documents[idx]
                    doc.metadata['rerank_score'] = score
                    reranked_docs.append(doc)

            # 确保结果不超过 top_k
            if top_k and len(reranked_docs) > top_k:
                reranked_docs = reranked_docs[:top_k]

            logger.info(f"Rerank 完成: {len(reranked_docs)} documents")
            return reranked_docs

        except Exception as e:
            logger.warning(f"Rerank API 调用失败: {e}, 使用降级排序")
            return self._fallback_sort(documents, top_k)

    def _fallback_sort(self, documents: List[Document], top_k: int = None) -> List[Document]:
        """降级排序：使用已有分数（向量相似度、标题匹配）"""
        def get_score(doc: Document) -> float:
            # 标题匹配分数大幅加权（标题直接反映文档主题，相关性极高）
            sim_score = doc.metadata.get('similarity_score', 0)
            if sim_score > 0:
                return sim_score * 2.0

            # 向量检索分数
            return doc.metadata.get('normalized_score',
                   doc.metadata.get('rrf_score',
                   doc.metadata.get('rerank_score', 0)))

        sorted_docs = sorted(documents, key=get_score, reverse=True)

        # 为降级排序的文档设置 rerank_score（使用加权分数）
        for doc in sorted_docs:
            if 'rerank_score' not in doc.metadata:
                doc.metadata['rerank_score'] = get_score(doc)

        if top_k:
            return sorted_docs[:top_k]
        return sorted_docs