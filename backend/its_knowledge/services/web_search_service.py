"""Web Search 兜底服务 — 知识库检索无结果时使用 Tavily API"""

import logging
import requests
from typing import List
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class WebSearchService:
    """Tavily Search API 封装，作为 RAG 检索兜底"""

    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, max_results: int = 5):
        self.api_key = api_key
        self.max_results = max_results

    def search(self, query: str) -> List[Document]:
        if not self.api_key:
            logger.warning("WEB_SEARCH_API_KEY 未配置，跳过联网搜索")
            return []

        try:
            response = requests.post(
                self.API_URL,
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": self.max_results,
                    "search_depth": "basic",
                },
                timeout=15,
            )
            response.raise_for_status()
            results = response.json().get("results", [])

            docs = []
            for r in results:
                doc = Document(
                    page_content=r.get("content", ""),
                    metadata={
                        "title": r.get("title", "Web Result"),
                        "source": r.get("url", ""),
                        "source_type": "web_search",
                        "rerank_score": 0.5,
                    },
                )
                docs.append(doc)

            logger.info(f"联网搜索返回 {len(docs)} 个结果: {query[:50]}...")
            return docs

        except requests.exceptions.Timeout:
            logger.warning("联网搜索超时")
            return []
        except Exception as e:
            logger.warning(f"联网搜索失败: {e}")
            return []
