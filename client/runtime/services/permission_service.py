"""目录权限管理服务

默认拒绝所有路径访问，用户需显式授权目录。
持久化存储在本地 SQLite 中。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from config import get_settings

router = APIRouter(prefix="/permissions", tags=["permissions"])

_permitted_paths: set[str] = set()
_PERMISSION_FILE = None


def _get_permission_file() -> Path:
    global _PERMISSION_FILE
    if _PERMISSION_FILE is None:
        settings = get_settings()
        _PERMISSION_FILE = Path(settings.data_dir) / "permissions.json"
    return _PERMISSION_FILE


def _load_permissions():
    global _permitted_paths
    pf = _get_permission_file()
    if pf.exists():
        try:
            data = json.loads(pf.read_text("utf-8"))
            _permitted_paths = set(data.get("paths", []))
            logger.info(f"[权限] 已加载 {len(_permitted_paths)} 个授权目录")
        except Exception as e:
            logger.warning(f"[权限] 加载失败: {e}")
            _permitted_paths = set()
    else:
        _permitted_paths = set()


def _save_permissions():
    pf = _get_permission_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(
        json.dumps({"paths": sorted(_permitted_paths)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_path_permitted(path: str) -> bool:
    """检查路径是否在授权目录下"""
    if not _permitted_paths:
        _load_permissions()

    resolved = str(Path(path).expanduser().resolve())
    return any(resolved.startswith(p) for p in _permitted_paths)


class GrantRequest(BaseModel):
    path: str


@router.post("/grant")
async def grant_permission(req: GrantRequest):
    resolved = str(Path(req.path).expanduser().resolve())
    p = Path(resolved)

    if not p.exists():
        return {"granted": False, "error": f"路径不存在: {req.path}"}

    if not p.is_dir():
        return {"granted": False, "error": "只能授权目录，不能授权单个文件"}

    _permitted_paths.add(resolved)
    _save_permissions()
    logger.info(f"[权限] 已授权目录: {resolved}")

    return {"granted": True, "path": resolved}


@router.delete("/revoke")
async def revoke_permission(req: GrantRequest):
    resolved = str(Path(req.path).expanduser().resolve())
    _permitted_paths.discard(resolved)
    _save_permissions()
    logger.info(f"[权限] 已撤销目录: {resolved}")
    return {"revoked": True, "path": resolved}


@router.get("/list")
async def list_permissions():
    if not _permitted_paths:
        _load_permissions()
    return {"paths": sorted(_permitted_paths)}
