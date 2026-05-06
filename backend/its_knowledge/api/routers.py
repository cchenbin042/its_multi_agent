import os.path
import logging
import shutil
import json
import time
import asyncio

import aiofiles
import jieba

from backend.its_knowledge.config import settings
from backend.its_knowledge.services.retrieval_service import RetrievalService, StepEvent
from backend.its_knowledge.services.agent_service import AgentService

logger = logging.getLogger(__name__)
from fastapi import APIRouter,UploadFile,File,HTTPException
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse
from backend.its_knowledge.services.ingestion.ingestion_processor import IngestionProcessor
from backend.its_knowledge.services.ingestion.document_loader_factory import DocumentLoaderFactory
from backend.its_knowledge.schemas.schema import UploadResponse, QueryResponse, QueryRequest, FeedbackRequest, DocumentListItem, DocumentPreviewResponse
from backend.its_knowledge.services.query_service import QueryService
from backend.its_knowledge.services.session_manager import SessionManager
from backend.its_knowledge.services.analytics_service import AnalyticsService
import  tempfile


def _extract_keywords(text: str, top_n: int = 5) -> list:
    """从问题文本中提取关键词（用于前端高亮）"""
    words = [w for w in jieba.cut(text) if len(w) >= 2]
    # 简单去重并保持顺序
    seen = set()
    result = []
    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:top_n]
# 1.创建APIRouter
router=APIRouter()
# 2. 创建应用的实例
ingestion_processor=IngestionProcessor()
query_service=QueryService()
retrieval_service=RetrievalService()
agent_service=AgentService()
session_manager=SessionManager()
analytics_service = AnalyticsService()

# IO(对文件读写) 执行SQL 网络请求 典型耗时任务
@router.post("/upload",response_model=UploadResponse,summary="处理知识库上传")
async def  upload_file(file: UploadFile=File(...)):
    """
    处理知识库上传

    支持的文件格式: .md, .txt, .pdf, .docx, .csv

    Args:
        file: 上传的文件

    Returns:
        UploadResponse: 上传结果

    Raises:
        HTTPException: 400 - 不支持的文件格式
        HTTPException: 500 - 文件处理失败
    """
    # 文件格式验证
    file_suffix = os.path.splitext(file.filename)[1].lower()
    if file_suffix not in DocumentLoaderFactory.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_suffix}，仅支持 {DocumentLoaderFactory.SUPPORTED_EXTENSIONS}"
        )

    # Initialize temp_file_path before try block for finally cleanup
    temp_file_path = ""

    try:
        # 临时目录
        tmp_md_dir= settings.TMP_FOLDER_PATH
        tmp_md_path = os.path.join(tmp_md_dir, file.filename)
        os.makedirs(tmp_md_dir, exist_ok=True)  # 确保目录存在

        # 1. 处理临时文件
        async with aiofiles.tempfile.NamedTemporaryFile(delete=False,suffix=file_suffix) as temp_file:

            # a. 读取上传文件的内容 # 对象（异步协程）缓冲区【1M】空间
            while content:=await file.read(1024*1024):
                # b. 将读取到上传文件的内容写入到临时文件
                await temp_file.write(content)

            # c. 获取临时文件的路径 # C:\Users\Administrator\AppData\Local\Temp\tmpe1puxhk7
            temp_file_path=temp_file.name

        shutil.move(temp_file_path, tmp_md_path)

        # 2. 磁盘写入完成,入库操作  # TODO(去重)
        chunks_added= await run_in_threadpool(ingestion_processor.ingest_file,tmp_md_path)
        logger.debug(f"临时文件路径:{tmp_md_path}")

        # 3. 入库后刷新所有缓存（P1优化：包括标题元数据缓存和 IDF 表）
        retrieval_service.refresh_cache()
        logger.info("入库完成，所有缓存已刷新")

        # 4.构建文件上传的响应对象
        return UploadResponse(
            status="success",
            message="文档上传知识库成功",
            file_name=file.filename,
            chunks_added=chunks_added
        )

    except Exception as e:
            raise HTTPException(status_code=500,detail=f"文件上传到知识库失败:{str(e)}")

    finally:
        # 4. 清空临时文件路径(磁盘空间不足)
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"临时文件:{temp_file_path}已删除...")



@router.post("/query",summary="处理用户问题查询",response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    处理用户问题查询（支持多轮对话）
    Args:
        request: 用户的输入请求

    Returns:

    """
    try:
        # 1、判断用户的输入
        user_question = request.question
        if not request.question:
            raise HTTPException(status_code=500, detail="用户问题不能为空")

        session_id = request.session_id

        # 2、获取历史对话
        history = session_manager.get_history(session_id) if session_id else None

        # 3、调用检索服务（P0优化：使用 run_in_threadpool 包装同步检索，避免阻塞事件循环）
        retrieval_context = await run_in_threadpool(retrieval_service.retrieval, user_question)

        # 4、调用查询服务
        answer = query_service.query(user_question, retrieval_context, history)

        # 5、保存对话历史
        if session_id:
            session_manager.add_message(session_id, "user", user_question)
            session_manager.add_message(session_id, "assistant", answer)

        # 6、返回结果
        return QueryResponse(
            question=request.question,
            answer=answer
        )

    except Exception as e:
        raise HTTPException(status_code=500,detail=f"查询失败:{str(e)}")


@router.post("/query/stream")
async def query_stream(request: QueryRequest):
    """
    流式查询（SSE）- 支持步骤事件推送

    事件类型:
    - step: 步骤状态变化 (started/completed)
    - token: LLM 流式输出
    - done: 完成，返回 sources 和总耗时
    """
    try:
        user_question = request.question
        if not user_question:
            raise HTTPException(status_code=500, detail="用户问题不能为空")

        session_id = request.session_id
        history = session_manager.get_history(session_id) if session_id else None

        async def generate():
            loop = asyncio.get_event_loop()
            step_queue = asyncio.Queue()
            global_start = time.perf_counter()
            retrieval_result = []  # 用列表包装以便在闭包中修改

            # 步骤回调：从同步线程安全地向异步队列发送事件
            def on_step(event: StepEvent):
                loop.call_soon_threadsafe(step_queue.put_nowait, event)

            # 检索任务（在后台线程执行，不阻塞）
            def do_retrieval():
                result, events = retrieval_service.retrieval_with_steps(user_question, on_step)
                retrieval_result.append(result)
                # 用 sentinel 标记检索完成
                loop.call_soon_threadsafe(step_queue.put_nowait, None)

            # 在后台线程启动检索（使用 asyncio.to_thread 确保并发）
            retrieval_future = asyncio.ensure_future(
                asyncio.to_thread(do_retrieval)
            )

            # 持续消费步骤事件，实时推送，直到收到 sentinel（None）
            while True:
                event = await step_queue.get()
                if event is None:
                    break  # 检索阶段完成
                yield {
                    "event": "step",
                    "data": json.dumps({
                        "step": event.step,
                        "status": event.status,
                        "duration_ms": event.duration_ms,
                        "detail": event.detail
                    }, ensure_ascii=False)
                }

            # 等待检索任务完成并获取结果
            await retrieval_future
            context = retrieval_result[0] if retrieval_result else []

            # ---- 步骤4: 生成回答 ----
            yield {
                "event": "step",
                "data": json.dumps({"step": "answer_generation", "status": "started"}, ensure_ascii=False)
            }

            t3 = time.perf_counter()
            full_answer = ""
            async for chunk in query_service.query_stream_async(user_question, context, history):
                if chunk:  # 只发送非空 chunk，避免空 token 事件
                    full_answer += chunk
                    yield {
                        "event": "token",
                        "data": json.dumps({"content": chunk}, ensure_ascii=False)
                    }

            # 步骤4 完成
            yield {
                "event": "step",
                "data": json.dumps({
                    "step": "answer_generation",
                    "status": "completed",
                    "duration_ms": int((time.perf_counter() - t3) * 1000)
                }, ensure_ascii=False)
            }

            # ---- 完成 ----
            if session_id:
                session_manager.add_message(session_id, "user", user_question)
                session_manager.add_message(session_id, "assistant", full_answer)

            total_dur = int((time.perf_counter() - global_start) * 1000)
            sources = [doc.metadata.get('title', '未知') for doc in context]
            keywords = _extract_keywords(user_question)
            yield {
                "event": "done",
                "data": json.dumps({
                    "sources": sources,
                    "matched_keywords": keywords,
                    "total_duration_ms": total_dur
                }, ensure_ascii=False)
            }

            # 记录查询分析数据
            analytics_service.record_query(
                question=user_question,
                session_id=session_id,
                answer_length=len(full_answer),
                num_sources=len(context),
                duration_ms=total_dur,
                final_count=len(context),
            )

        return EventSourceResponse(generate())

    except Exception as e:
        logger.error(f"查询失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/query/agent")
async def query_agent(request: QueryRequest):
    """
    Agent 深度推理模式（SSE）— 支持多步工具调用

    事件类型:
    - step: agent 轮次状态（含 tool_calls 详情）
    - token: 最终回答流式输出
    - done: 完成，返回 sources 和总耗时
    """
    try:
        user_question = request.question
        if not user_question:
            raise HTTPException(status_code=500, detail="用户问题不能为空")

        session_id = request.session_id
        history = session_manager.get_history(session_id) if session_id else None

        async def generate():
            global_start = time.perf_counter()

            async for event in agent_service.run_stream(user_question, history):
                # agent_service 的 data 字段已经是 JSON 字符串
                event_type = event["event"]
                data_str = event["data"]
                yield {
                    "event": event_type,
                    "data": data_str,
                }

            # 保存会话
            if session_id:
                session_manager.add_message(session_id, "user", user_question)
                # Note: agent full_answer 不在这个闭包里，所以这里只记录用户消息
                # 完整记录需要在 agent_service 内部处理或通过 done 事件获取

        return EventSourceResponse(generate())

    except Exception as e:
        logger.error(f"Agent 查询失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agent 查询失败: {str(e)}")


@router.post("/cache/clear", summary="清空查询缓存")
async def clear_cache():
    """清空查询缓存（手动触发）"""
    retrieval_service.clear_cache()
    return {"status": "success", "message": "查询缓存已清空"}


@router.post("/feedback", summary="提交用户反馈")
async def submit_feedback(request: FeedbackRequest):
    """记录用户对回答的正向/负向反馈（写入 analytics.db）"""
    await run_in_threadpool(
        analytics_service.record_feedback,
        message_id=request.message_id,
        session_id=request.session_id,
        question=request.question,
        rating=request.rating,
        comment=request.comment or "",
        sources=json.dumps(request.sources, ensure_ascii=False) if request.sources else "",
    )
    logger.info(f"反馈已记录: rating={request.rating}, question={request.question[:50]}...")
    return {"status": "success", "message": "反馈已提交"}


@router.get("/feedback/stats", summary="反馈统计")
async def get_feedback_stats(days: int = 7):
    """获取用户反馈分析数据"""
    return await run_in_threadpool(analytics_service.get_feedback_stats, days)


@router.get("/documents", summary="文档列表（分页 + 搜索）")
async def list_documents(offset: int = 0, limit: int = 20, search: str = ""):
    """获取已入库文档列表，支持分页和标题搜索"""
    docs, total = await run_in_threadpool(
        retrieval_service.full_doc_store.list_all, offset, limit, search
    )
    return {"documents": docs, "total": total, "offset": offset, "limit": limit}


@router.delete("/documents/{title:path}", summary="删除文档")
async def delete_document(title: str):
    """按标题删除文档并刷新缓存"""
    success = await run_in_threadpool(
        retrieval_service.full_doc_store.delete_by_title, title
    )
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    retrieval_service.refresh_cache()
    return {"status": "success", "message": f"文档 '{title}' 已删除"}


@router.get("/documents/{title:path}", summary="文档内容预览")
async def preview_document(title: str):
    """获取文档内容预览（前 1000 字符）"""
    content = await run_in_threadpool(
        retrieval_service.full_doc_store.get_preview, title
    )
    if content is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"title": title, "content_preview": content}


@router.get("/conversations", summary="历史会话列表")
async def list_conversations(limit: int = 20):
    """获取最近的会话列表"""
    return await run_in_threadpool(session_manager.list_sessions, limit)


@router.get("/conversations/{session_id:path}", summary="会话消息详情")
async def get_conversation(session_id: str):
    """获取指定会话的所有消息"""
    return await run_in_threadpool(session_manager.get_session_messages, session_id)


@router.delete("/conversations/{session_id:path}", summary="删除会话")
async def delete_conversation(session_id: str):
    """删除指定会话"""
    await run_in_threadpool(session_manager.clear_session, session_id)
    return {"status": "success", "message": "会话已删除"}


@router.get("/stats", summary="查询统计")
async def get_stats(days: int = 7):
    """获取查询分析聚合数据"""
    return await run_in_threadpool(analytics_service.get_stats, days)



