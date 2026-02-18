"""本地存储管理

使用 ChromaDB 作为本地向量数据库，持久化到磁盘。
支持多 collection（按项目/场景分区）。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from config import get_settings

_chroma_client = None


async def init_store():
    """初始化 ChromaDB 持久化客户端"""
    global _chroma_client
    settings = get_settings()
    persist_dir = str(Path(settings.data_dir) / "chroma_db")
    Path(persist_dir).mkdir(parents=True, exist_ok=True)

    import chromadb

    _chroma_client = chromadb.PersistentClient(path=persist_dir)
    logger.info(f"[存储] ChromaDB 初始化完成，路径: {persist_dir}")


async def close_store():
    global _chroma_client
    _chroma_client = None


async def get_collection(name: str = "default"):
    """获取或创建一个 collection"""
    if _chroma_client is None:
        await init_store()
    return _chroma_client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


async def delete_collection(name: str):
    """删除 collection"""
    if _chroma_client is None:
        await init_store()
    try:
        _chroma_client.delete_collection(name=name)
        logger.info(f"[存储] 已删除 collection: {name}")
    except Exception as e:
        logger.warning(f"[存储] 删除 collection 失败: {name} -> {e}")


async def list_collections() -> list[str]:
    """列出所有 collection"""
    if _chroma_client is None:
        await init_store()
    return [c.name for c in _chroma_client.list_collections()]
