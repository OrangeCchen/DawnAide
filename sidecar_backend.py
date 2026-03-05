"""
AgentTeams Backend Sidecar 入口点（供 PyInstaller 使用）

直接传递 app 对象给 uvicorn，避免 frozen 模式下无法按字符串解析模块路径。
"""
from __future__ import annotations

import sys

if __name__ == "__main__":
    import uvicorn
    from src.main import app
    from src.config import get_settings

    settings = get_settings()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=settings.server.port,
        reload=False,
        log_level=settings.server.log_level.lower(),
    )
