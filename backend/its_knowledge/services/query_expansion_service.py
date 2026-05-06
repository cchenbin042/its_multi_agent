# backend/its_knowledge/services/query_expansion_service.py
import json
import logging
import os
from typing import List

from langchain_openai import ChatOpenAI

from backend.its_knowledge.config.settings import settings

logger = logging.getLogger(__name__)


class QueryExpansionService:
    """
    查询扩展服务

    支持两种扩展方式：
    1. 词典扩展：基于同义词词典替换/扩展关键词
    2. LLM 改写：调用 LLM 生成问题变体（用于复杂问题）
    """

    MULTI_INTENT_KEYWORDS = ["同时", "又", "而且", "并且", "另外", "还"]

    def __init__(self):
        self.synonym_dict = self._load_synonyms()
        self.llm = ChatOpenAI(
            model_name=settings.MODEL,
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            temperature=0.3,
        )

    def _load_synonyms(self) -> dict:
        """加载同义词词典"""
        try:
            if os.path.exists(settings.SYNONYM_FILE_PATH):
                with open(settings.SYNONYM_FILE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            logger.warning(f"同义词词典文件不存在: {settings.SYNONYM_FILE_PATH}")
            return {}
        except Exception as e:
            logger.error(f"加载同义词词典失败: {e}")
            return {}

    def expand(self, user_question: str) -> List[str]:
        """
        执行查询扩展

        Args:
            user_question: 用户原始问题

        Returns:
            List[str]: 扩展后的查询列表（不含原始问题，调用端需自行拼接）
        """
        queries = []

        # 1. 词典扩展
        synonym_queries = self._synonym_expand(user_question)
        queries.extend(synonym_queries)

        # 2. 判断是否需要 LLM 改写
        if self._need_llm_rewrite(user_question, synonym_queries):
            try:
                llm_queries = self._llm_rewrite(user_question)
                queries.extend(llm_queries)
            except Exception as e:
                logger.warning(f"LLM 改写失败: {e}")

        # 3. 限制数量
        max_queries = settings.MAX_EXPANSION_QUERIES + 1
        return queries[:max_queries]

    def _synonym_expand(self, question: str) -> List[str]:
        """基于同义词词典扩展查询"""
        expanded = []

        for term, synonyms in self.synonym_dict.items():
            if term in question:
                for syn in synonyms:
                    if syn != term:
                        new_query = question.replace(term, syn)
                        expanded.append(new_query)

        return expanded

    def _need_llm_rewrite(self, question: str, synonym_queries: List[str]) -> bool:
        """判断是否需要 LLM 改写"""
        if not settings.ENABLE_LLM_REWRITE:
            return False

        if len(question) > settings.LLM_REWRITE_THRESHOLD:
            return True

        if len(synonym_queries) == 0:
            return True

        for keyword in self.MULTI_INTENT_KEYWORDS:
            if keyword in question:
                return True

        return False

    def _llm_rewrite(self, question: str) -> List[str]:
        """调用 LLM 生成问题变体"""
        prompt = f"""
用户问题：{question}

请生成 2-3 个语义相近但表述不同的问题变体，用于检索知识库。
要求：
1. 保持原问题意图不变
2. 使用不同词汇表达相同含义
3. 拆解复杂问题为具体子问题

输出格式（JSON数组）：
["变体1", "变体2", ...]
"""

        response = self.llm.invoke(prompt)

        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                content = content.rsplit("```", 1)[0]

            queries = json.loads(content)
            return [q.strip() for q in queries if q.strip()]
        except json.JSONDecodeError as e:
            logger.warning(f"解析 LLM 响应失败: {e}, 响应内容: {response.content}")
            return []