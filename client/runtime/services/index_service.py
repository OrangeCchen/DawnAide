"""本地知识库索引服务

负责文档分块、向量化、写入本地向量库（ChromaDB）。
支持增量索引与全量重建。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from config import get_settings
from services.permission_service import is_path_permitted

router = APIRouter(prefix="/kb", tags=["kb"])

# 支持索引的文件类型
INDEXABLE_EXTENSIONS = {
    ".txt", ".md", ".rst",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp",
    ".json", ".yaml", ".yml", ".toml",
    ".html", ".css",
    ".docx", ".pdf",
}

_running_tasks: dict[str, dict] = {}


class IndexRequest(BaseModel):
    paths: list[str]
    collection: str = "default"
    reindex: bool = False
    file_types: list[str] | None = None


class IndexResponse(BaseModel):
    task_id: str
    accepted: bool
    message: str = ""


@router.post("/index", response_model=IndexResponse)
async def submit_index_task(req: IndexRequest):
    for p in req.paths:
        resolved = str(Path(p).expanduser().resolve())
        if not is_path_permitted(resolved):
            raise HTTPException(status_code=403, detail=f"路径未授权: {p}")

    task_id = str(uuid.uuid4())[:8]
    _running_tasks[task_id] = {"status": "running", "progress": 0}

    asyncio.create_task(_run_index(task_id, req))

    return IndexResponse(task_id=task_id, accepted=True, message="索引任务已开始")


@router.get("/index/status/{task_id}")
async def get_index_status(task_id: str):
    task = _running_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


async def _run_index(task_id: str, req: IndexRequest):
    """后台执行索引任务"""
    settings = get_settings()
    try:
        files = _collect_files(req.paths, req.file_types)
        total = len(files)
        logger.info(f"[索引任务 {task_id}] 收集到 {total} 个文件")

        if total == 0:
            _running_tasks[task_id] = {"status": "done", "progress": 100, "indexed": 0}
            return

        from store.local_store import get_collection

        collection = await get_collection(req.collection)

        indexed = 0
        for i, file_path in enumerate(files):
            try:
                chunks = await _chunk_file(file_path, settings.chunk_size, settings.chunk_overlap)
                if not chunks:
                    continue

                ids = []
                documents = []
                metadatas = []

                for j, chunk in enumerate(chunks):
                    content_hash = hashlib.md5(chunk.encode()).hexdigest()[:12]
                    doc_id = f"{file_path.stem}_{content_hash}_{j}"
                    ids.append(doc_id)
                    documents.append(chunk)
                    metadatas.append({
                        "source": str(file_path),
                        "chunk_index": j,
                        "total_chunks": len(chunks),
                    })

                await asyncio.to_thread(
                    collection.upsert,
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
                indexed += 1

            except Exception as e:
                logger.warning(f"[索引任务 {task_id}] 文件索引失败: {file_path} -> {e}")

            _running_tasks[task_id] = {
                "status": "running",
                "progress": int((i + 1) / total * 100),
                "indexed": indexed,
                "total": total,
            }

        _running_tasks[task_id] = {
            "status": "done",
            "progress": 100,
            "indexed": indexed,
            "total": total,
        }
        logger.info(f"[索引任务 {task_id}] 完成，索引 {indexed}/{total} 个文件")

    except Exception as e:
        logger.error(f"[索引任务 {task_id}] 异常: {e}")
        _running_tasks[task_id] = {"status": "error", "error": str(e)}


def _collect_files(
    paths: list[str],
    file_types: list[str] | None = None,
) -> list[Path]:
    """递归收集待索引文件"""
    allowed_ext = set(file_types) if file_types else INDEXABLE_EXTENSIONS
    result = []

    for raw_path in paths:
        p = Path(raw_path).expanduser().resolve()
        if p.is_file() and p.suffix.lower() in allowed_ext:
            result.append(p)
        elif p.is_dir():
            for fp in p.rglob("*"):
                if fp.is_file() and fp.suffix.lower() in allowed_ext:
                    if not any(part.startswith(".") for part in fp.relative_to(p).parts):
                        result.append(fp)

    return result


async def _chunk_file(
    file_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """将文件内容按固定大小分块"""
    from services.file_service import _read_file_content

    content = _read_file_content(file_path, None, None)
    if not content or content.startswith("[错误]"):
        return []

    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - chunk_overlap

    return chunks
