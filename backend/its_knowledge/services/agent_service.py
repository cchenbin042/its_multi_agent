"""ReAct Agent 模式 — 将知识库检索包装为 tool，支持多步推理"""

import json
import re
import time
import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

import jieba

from backend.its_knowledge.config.settings import settings
from backend.its_knowledge.services.retrieval_service import RetrievalService
from backend.its_knowledge.utils.brand_anonymizer import BrandAnonymizer

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """你是 ITS 技术支持助手。你可以使用 search_knowledge_base 工具在 ITS 知识库中搜索技术文档。

工作流程：
1. 分析用户的问题，确定需要查找哪些关键词
2. 调用 search_knowledge_base 搜索相关知识
3. 如果搜索结果不够充分，用不同的关键词再次搜索
4. 综合所有搜索结果，给出完整、准确的回答

【推理要求】：
- 在每次调用工具之前，请先输出一段简短的思考（1-2 句话），说明你为什么要搜索这些关键词以及期望找到什么信息。
- 思考内容请放在  response标签中。

【回答要求】：
1. **基于事实**：严格基于 search_knowledge_base 返回的搜索结果回答，严禁编造搜索结果中未提及的信息，严禁使用自身训练数据。如果多次搜索均未找到相关信息，请直接回答："当前的知识库中暂时没有找到该问题的解决方案。"
2. **结合历史**：如果用户问题是追问，请结合历史对话理解真实意图。
3. **去特定化处理**：(重要)
    - 除非用户问题中明确指明了特定型号/品牌，否则在回答中请移除或替换具体的设备型号、品牌名称（如"联想"、"K900"等）。
    - 例如：将"联想手机设置"泛化为"手机设置"；将"打开联想电脑管家"泛化为"打开系统管理软件"或"相关设置工具"。
4. **结构清晰**：
    - 如果是操作步骤，请使用有序列表（1. 2. 3.）。
    - 语言风格应简洁、专业、直接，避免寒暄和废话。
5. 引用来源：在回答的最后，请列出你参考的搜索结果编号（如 [1]、[2]）。"""


def _extract_reasoning(response) -> str:
    """从 LLM 响应中提取推理过程"""
    # 方式1: 检查 additional_kwargs 中的 reasoning_content（DeepSeek 等模型）
    if hasattr(response, 'additional_kwargs') and response.additional_kwargs:
        reasoning = response.additional_kwargs.get('reasoning_content', '')
        if reasoning:
            return reasoning.strip()

    # 方式2: 从 AIMessage.content 中解析  response... 标签
    if hasattr(response, 'content') and response.content:
        match = re.search(
            r'<reasoning>(.*?)</reasoning>',
            response.content,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

    return ""


class AgentService:
    """ReAct Agent: 将检索能力包装为 tool，支持多步推理"""

    MAX_ITERATIONS = 5

    def __init__(self):
        self.retrieval = RetrievalService()
        self.llm = ChatOpenAI(
            model_name=settings.MODEL,
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            temperature=0,
        )
        self.anonymizer = BrandAnonymizer(settings.BRAND_MAP_FILE)

    def _create_tools(self):
        retrieval_svc = self.retrieval
        found_useful = [False]

        @tool
        def search_knowledge_base(query: str) -> str:
            """
            在 ITS 知识库中搜索技术文档。当你需要查找特定技术问题的
            解决方案、操作步骤或配置说明时使用此工具。

            Args:
                query: 搜索关键词或问题描述
            """
            docs = retrieval_svc.retrieval(query)
            if not docs:
                return "[未找到相关文档]"

            found_useful[0] = True
            top_docs = docs[:5]
            total_budget = 8000
            floor = 500

            scores = []
            for doc in top_docs:
                score = doc.metadata.get('rerank_score', None)
                scores.append(score)

            has_scores = all(s is not None for s in scores)

            if has_scores and sum(scores) > 0:
                weights = [s / sum(scores) for s in scores]
                allocations = [max(floor, int(total_budget * w)) for w in weights]

                total_alloc = sum(allocations)
                if total_alloc > total_budget:
                    scale = total_budget / total_alloc
                    allocations = [max(floor, int(a * scale)) for a in allocations]
            else:
                allocations = [total_budget // len(top_docs) for _ in top_docs]

            parts = []
            for i, doc in enumerate(top_docs):
                title = doc.metadata.get('title', 'Unknown')
                max_chars = allocations[i]
                content = doc.page_content[:max_chars]
                parts.append(f"### [{i+1}] {title}\n{content}")
            return "\n\n".join(parts)

        return [search_knowledge_base], found_useful

    async def run_stream(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        异步流式执行 Agent，yield SSE event dicts:
        { "event": "step"|"token"|"done"|"error", "data": {...} }
        """
        # 构建消息列表
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
        if history:
            for msg in history[-10:]:
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant':
                    messages.append(AIMessage(content=msg['content']))
        messages.append(HumanMessage(content=question))

        start_time = time.perf_counter()
        tools, found_useful = self._create_tools()
        tool_map = {t.name: t for t in tools}
        tool_names = [t.name for t in tools]

        iteration = 0
        full_answer = ""
        has_any_tool_call = False  # 跟踪是否至少调用过一次工具

        try:
            # 绑定 tools 到 LLM
            llm_with_tools = self.llm.bind_tools(tools)

            while iteration < self.MAX_ITERATIONS:
                iteration += 1

                # 发送搜索步骤事件
                yield {
                    "event": "step",
                    "data": json.dumps({
                        "step": f"agent_round_{iteration}",
                        "status": "running",
                        "detail": {"round": iteration},
                    }, ensure_ascii=False),
                }

                # 调用 LLM
                response = llm_with_tools.invoke(messages)
                reasoning = _extract_reasoning(response)

                # 检查是否有 tool calls
                if response.tool_calls:
                    has_any_tool_call = True
                    tool_calls_info = []
                    for tc in response.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_args = tc.get("args", {})
                        query_arg = tool_args.get("query", str(tool_args))
                        tool_calls_info.append({
                            "tool": tool_name,
                            "query": query_arg,
                        })

                        # 执行工具
                        if tool_name in tool_map:
                            tool_result = tool_map[tool_name].invoke(tool_args)
                            messages.append(response)
                            messages.append({
                                "role": "tool",
                                "content": tool_result,
                                "tool_call_id": tc["id"]
                                if "id" in tc
                                else f"call_{iteration}",
                            })

                    yield {
                        "event": "step",
                        "data": json.dumps({
                            "step": f"agent_round_{iteration}",
                            "status": "completed",
                            "detail": {
                                "round": iteration,
                                "tool_calls": tool_calls_info,
                                "reasoning": reasoning,
                            },
                        }, ensure_ascii=False),
                    }
                else:
                    # LLM 决定直接回答（不再调用工具）
                    yield {
                        "event": "step",
                        "data": json.dumps({
                            "step": f"agent_round_{iteration}",
                            "status": "completed",
                            "detail": {"round": iteration, "final": True},
                        }, ensure_ascii=False),
                    }

                    # 硬兜底：如果所有搜索均未找到有效内容，强制返回统一话术
                    if not found_useful[0]:
                        full_answer = "当前的知识库中暂时没有找到该问题的解决方案。"
                    else:
                        full_answer = response.content or ""

                    full_answer = self.anonymizer.anonymize(full_answer)
                    # 模拟流式输出（按 chunk 发送 token）
                    chunk_size = 20
                    for i in range(0, len(full_answer), chunk_size):
                        chunk = full_answer[i:i + chunk_size]
                        yield {
                            "event": "token",
                            "data": json.dumps(
                                {"content": chunk}, ensure_ascii=False
                            ),
                        }
                    break
            else:
                # 达到最大迭代次数
                if not found_useful[0]:
                    full_answer = "当前的知识库中暂时没有找到该问题的解决方案。"
                else:
                    full_answer = "已达到最大搜索轮次，基于已获取的信息：\n"
                    final_response = llm_with_tools.invoke(
                        messages + [HumanMessage(
                            content="请基于以上所有搜索结果，给用户一个综合回答。"
                        )]
                    )
                    full_answer += final_response.content or ""
                full_answer = self.anonymizer.anonymize(full_answer)
                for i in range(0, len(full_answer), 20):
                    chunk = full_answer[i:i + 20]
                    yield {
                        "event": "token",
                        "data": json.dumps(
                            {"content": chunk}, ensure_ascii=False
                        ),
                    }

        except Exception as e:
            logger.error(f"Agent 执行异常: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}, ensure_ascii=False),
            }

        # 完成事件
        total_dur = int((time.perf_counter() - start_time) * 1000)
        # 提取关键词用于前端高亮
        kw_list = [w for w in jieba.cut(question) if len(w) >= 2]
        seen_kw = set()
        keywords = []
        for w in kw_list:
            if w not in seen_kw:
                seen_kw.add(w)
                keywords.append(w)
        yield {
            "event": "done",
            "data": json.dumps({
                "sources": [],
                "matched_keywords": keywords[:5],
                "total_duration_ms": total_dur,
            }, ensure_ascii=False),
        }
