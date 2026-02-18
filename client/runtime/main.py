"""AgentTeams Client Runtime — 本地能力服务

轻量级 FastAPI 服务，运行在用户设备上，提供：
- 本地文件读取与目录浏览
- 本地知识库索引与检索
- 目录权限管理

仅监听 127.0.0.1，通过短期 token 认证。
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from config import RuntimeSettings, get_settings

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(f"AgentTeams Client Runtime v{settings.version} 启动")
    logger.info(f"监听: {settings.host}:{settings.port}")
    logger.info(f"数据目录: {settings.data_dir}")
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    from store.local_store import init_store
    await init_store()
    logger.info("本地存储已初始化")

    yield
    from store.local_store import close_store
    await close_store()
    logger.info("Client Runtime 已关闭")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AgentTeams Client Runtime",
        description="本地能力服务 — 文件处理、知识库索引与检索",
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- 路由注册 ---

    from services.file_service import router as file_router
    from services.index_service import router as index_router
    from services.retrieval_service import router as retrieval_router
    from services.permission_service import router as permission_router

    app.include_router(file_router)
    app.include_router(index_router)
    app.include_router(retrieval_router)
    app.include_router(permission_router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "version": settings.version,
            "capabilities": ["file", "kb", "permission"],
        }

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"未处理异常: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": str(exc)},
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
