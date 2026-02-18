"""FastAPI 应用入口"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.config import ROOT_DIR, get_settings

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    from src.init import initialize_app

    await initialize_app()
    yield
    # 关闭数据库连接
    from src.storage.database import close_database
    await close_database()
    logger.info("应用关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title="AgentTeams - 数字员工协作平台",
        description="多Agent团队协作引擎 POC",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    from src.api.routes import router
    from src.api.websocket import ws_router
    from src.api.kb import router as kb_router

    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(kb_router)

    # 静态文件（前端构建产物）- 挂载 assets 子目录
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Catch-all: 所有非 API/WS 请求返回 index.html（SPA 路由支持）
    @app.get("/{full_path:path}")
    async def serve_frontend(request: Request, full_path: str):
        # 排除 API 和 WS 路径
        if full_path.startswith("api/") or full_path.startswith("ws"):
            return HTMLResponse(status_code=404, content="Not found")

        # 尝试返回具体静态文件
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # 否则返回 index.html
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)

        # 无前端构建产物时返回提示
        return HTMLResponse(
            content="""
            <html>
            <head><title>AgentTeams</title></head>
            <body style="background:#1a1a2e;color:#e0e0e0;font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
            <div style="text-align:center;">
                <h1>AgentTeams - 数字员工协作平台</h1>
                <p style="color:#a0a0a0;">后端已启动，前端尚未构建。</p>
                <p style="color:#a0a0a0;">请执行: <code style="background:#2a3a4e;padding:2px 8px;border-radius:4px;">cd frontend && npm run build</code></p>
                <p style="color:#a0a0a0;margin-top:16px;">或使用开发模式: <code style="background:#2a3a4e;padding:2px 8px;border-radius:4px;">cd frontend && npm run dev</code></p>
                <hr style="border-color:#2a3a4e;margin:24px 0;">
                <p style="color:#666;">API 文档: <a href="/docs" style="color:#4a9eff;">/docs</a></p>
            </div>
            </body>
            </html>
            """,
            status_code=200,
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        log_level=settings.server.log_level.lower(),
    )
