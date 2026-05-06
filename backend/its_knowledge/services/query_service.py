from typing import List, Dict, Any, Optional, Iterator, AsyncGenerator
import logging

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from backend.its_knowledge.config import settings
from backend.its_knowledge.utils.brand_anonymizer import BrandAnonymizer

# P1优化：引入 tiktoken 做 token 计数
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken 未安装，将使用字符数估算 token")

logger = logging.getLogger(__name__)


class QueryService:
    """检索服务"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model_name=settings.MODEL,
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            temperature=0,
        )
        # P1优化：初始化 tiktoken encoder
        if TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.encoding_for_model(settings.MODEL)
            except KeyError:
                self._encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self._encoder = None
        self.anonymizer = BrandAnonymizer(settings.BRAND_MAP_FILE)

    def _count_tokens(self, text: str) -> int:
        """
        P1优化：计算文本的 token 数量
        """
        if self._encoder:
            return len(self._encoder.encode(text))
        else:
            # 降级方案：中文约 1.5 字符/token，英文约 4 字符/token
            # 简化估算：总字符数 / 2
            return len(text) // 2

    def _build_context_with_token_limit(
        self,
        retrival_context: List[Document]
    ) -> str:
        """
        按 rerank_score 动态分配 token 预算

        Args:
            retrival_context: 检索结果文档列表（已按相关性排序）

        Returns:
            str: 拼接后的上下文字符串
        """
        if not retrival_context:
            return ""

        total_budget = settings.CONTEXT_TOKEN_LIMIT
        floor = settings.CONTEXT_TOKEN_FLOOR
        n = len(retrival_context)

        scores = []
        for doc in retrival_context:
            score = doc.metadata.get('rerank_score', None)
            scores.append(score)

        has_scores = all(s is not None for s in scores)

        if has_scores and sum(scores) > 0:
            weights = [s / sum(scores) for s in scores]
            allocations = []
            for w in weights:
                alloc = max(floor, int(total_budget * w))
                allocations.append(alloc)

            total_alloc = sum(allocations)
            if total_alloc > total_budget:
                scale = total_budget / total_alloc
                allocations = [max(floor, int(a * scale)) for a in allocations]
        else:
            allocations = [max(floor, total_budget // n) for _ in range(n)]

        context_parts = []
        used = 0
        for idx, doc in enumerate(retrival_context):
            budget = allocations[idx]
            remaining = total_budget - used
            if remaining < floor:
                break
            budget = min(budget, remaining)

            content = doc.page_content
            doc_header = f"资料{idx + 1}:"
            header_tokens = self._count_tokens(doc_header)
            available = budget - header_tokens
            if available <= 0:
                available = budget

            if idx == 0 and self._count_tokens(content) > available:
                truncate_ratio = available / max(1, self._count_tokens(content))
                truncate_chars = int(len(content) * truncate_ratio)
                truncated = f"{doc_header}{content[:truncate_chars]}..."
                context_parts.append(truncated)
                used += self._count_tokens(truncated)
                logger.warning(f"第一篇文档超限，截断至 {truncate_chars} 字符")
                continue

            full_text = f"{doc_header}{content}"
            if self._count_tokens(full_text) <= budget:
                context_parts.append(full_text)
                used += self._count_tokens(full_text)
            else:
                truncate_ratio = available / max(1, self._count_tokens(content))
                truncate_chars = int(len(content) * truncate_ratio)
                truncated = f"{doc_header}{content[:truncate_chars]}"
                context_parts.append(truncated)
                used += self._count_tokens(truncated)
                break

        logger.info(f"上下文构建完成: {len(context_parts)} 篇文档, {used} tokens")
        return "\n\n".join(context_parts)

    SYSTEM_PROMPT = """你是一位经验丰富的高级技术支持专家。请基于提供的【参考资料】回答用户问题。

【回答要求】：
1. **基于事实**：严格基于【参考资料】的内容回答，严禁编造资料中未提及的信息。如果资料无法回答问题，请直接回答："当前的知识库中暂时没有找到该问题的解决方案。"
2. **结合历史**：如果用户问题是追问，请结合历史对话理解真实意图。
3. **去特定化处理**：(重要)
    - 除非用户问题中明确指明了特定型号/品牌，否则在回答中请**移除**或**替换**具体的设备型号、品牌名称（如"联想"、"K900"等）。
    - 例如：将"联想手机设置"泛化为"手机设置"；将"打开联想电脑管家"泛化为"打开系统管理软件"或"相关设置工具"。
4. **结构清晰**：
    - 如果是操作步骤，请使用有序列表（1. 2. 3.）。
    - 语言风格应简洁、专业、直接，避免寒暄和废话。
5. 引用来源：在回答的最后，请列出你参考的【资料x】的编号(仅列出编号即可)"""

    def _build_messages(
        self,
        user_question: str,
        context_str: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> List:
        """
        修复：使用 Message 结构构建 prompt，而非纯字符串拼接

        Args:
            user_question: 用户问题
            context_str: 参考资料上下文
            history: 对话历史

        Returns:
            List[Message]: LangChain Message 列表
        """
        messages = []

        # 1. 系统指令
        messages.append(SystemMessage(content=self.SYSTEM_PROMPT))

        # 2. 参考资料作为第一个 HumanMessage
        context_message = f"【参考资料】：\n```\n{context_str}\n```\n\n【用户问题】：\n```\n{user_question}\n```\n\n请基于参考资料回答用户问题。"
        messages.append(HumanMessage(content=context_message))

        # 3. 历史对话（如果有）
        if history:
            for msg in history[-10:]:
                role = msg.get('role', '')
                content = msg.get('content', '')
                if role == 'user':
                    messages.append(HumanMessage(content=content))
                elif role == 'assistant':
                    messages.append(AIMessage(content=content))

        return messages

    def query(
        self,
        user_question: str,
        retrival_context: List[Document],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        根据用户问题和知识库上下文，生成回答

        Args:
            user_question: 用户问题
            retrival_context: 知识库上下文
            history: 对话历史（可选）

        Returns:
            答案
        """
        # 1、判断是否检索到了文档
        if not retrival_context:
            return '未检索到相关知识库'

        # P1优化：使用 token 限制的上下文构建
        context_str = self._build_context_with_token_limit(retrival_context)

        # 修复：使用 Message 结构而非纯字符串拼接
        messages = self._build_messages(user_question, context_str, history)
        llm_response = self.llm.invoke(messages)

        # 返回模型结果
        return self.anonymizer.anonymize(llm_response.content)

    def query_stream(
        self,
        user_question: str,
        retrival_context: List[Document],
        history: Optional[List[Dict[str, str]]] = None
    ) -> Iterator[str]:
        """
        流式生成回答

        Args:
            user_question: 用户问题
            retrival_context: 知识库上下文
            history: 对话历史（可选）

        Yields:
            str: 每个生成的token片段
        """
        # 1、判断是否检索到了文档
        if not retrival_context:
            yield '未检索到相关知识库'
            return

        # P1优化：使用 token 限制的上下文构建
        context_str = self._build_context_with_token_limit(retrival_context)

        # 修复：使用 Message 结构而非纯字符串拼接
        messages = self._build_messages(user_question, context_str, history)
        full_response = ""
        for chunk in self.llm.stream(messages):
            full_response += chunk.content

        full_response = self.anonymizer.anonymize(full_response)
        chunk_size = 20
        for i in range(0, len(full_response), chunk_size):
            yield full_response[i:i + chunk_size]

    async def query_stream_async(
        self,
        user_question: str,
        retrival_context: List[Document],
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式生成回答（异步版本，推荐使用）

        Args:
            user_question: 用户问题
            retrival_context: 知识库上下文
            history: 对话历史（可选）

        Yields:
            str: 每个生成的token片段
        """
        # 1、判断是否检索到了文档
        if not retrival_context:
            yield '未检索到相关知识库'
            return

        # P1优化：使用 token 限制的上下文构建
        context_str = self._build_context_with_token_limit(retrival_context)

        # 修复：使用 Message 结构而非纯字符串拼接
        messages = self._build_messages(user_question, context_str, history)
        full_response = ""
        async for chunk in self.llm.astream(messages):
            full_response += chunk.content

        full_response = self.anonymizer.anonymize(full_response)
        chunk_size = 20
        for i in range(0, len(full_response), chunk_size):
            yield full_response[i:i + chunk_size]