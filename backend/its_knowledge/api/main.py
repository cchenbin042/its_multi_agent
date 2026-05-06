"""
创建FastAPI实例 并且管理所有的路由
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from backend.its_knowledge.api.routers import router
from backend.its_knowledge.utils.logging_config import setup_logging, request_id_ctx

setup_logging()
logger = logging.getLogger(__name__)


def create_fast_api() -> FastAPI:
    # 1. 创建FastApi实例
    app = FastAPI(title="Knowledge API")

    # 2. 添加 CORS 中间件（允许前端开发环境跨域访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. 请求追踪中间件 — 为每个请求分配唯一 ID
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        request_id_ctx.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    # 4. 注册各种路由
    app.include_router(router=router)

    # 5. 返回创建的FastAPI
    return app


if __name__ == '__main__':
    import uvicorn
    logger.info("准备启动Web服务器...")
    try:
        uvicorn.run(app=create_fast_api(), host="127.0.0.1", port=8001)
        logger.info("Web服务器启动成功")
    except KeyboardInterrupt:
        logger.info("Web服务器已停止")
    except Exception as e:
        logger.error(f"Web服务器启动失败: {e}")
