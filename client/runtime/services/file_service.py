"""本地文件服务

提供文件读取、目录浏览、格式转换等能力。
仅允许访问已授权目录下的文件。
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
import subprocess

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from services.permission_service import is_path_permitted

router = APIRouter(prefix="/file", tags=["file"])


class FileReadRequest(BaseModel):
    path: str
    start: int | None = None
    end: int | None = None
    mode: str = "text"  # text | binary | list


class FileReadResponse(BaseModel):
    content: str = ""
    mime: str = "text/plain"
    meta: dict = {}
    entries: list[dict] = []
    error: str = ""


class OpenPathRequest(BaseModel):
    path: str


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/read", response_model=FileReadResponse)
async def read_file(req: FileReadRequest):
    p = Path(req.path).expanduser().resolve()

    if not is_path_permitted(str(p)):
        raise HTTPException(status_code=403, detail=f"路径未授权: {req.path}")

    if not p.exists():
        return FileReadResponse(error=f"路径不存在: {req.path}")

    if req.mode == "list":
        return _list_directory(p)

    if not p.is_file():
        return FileReadResponse(error=f"不是文件: {req.path}")

    stat = p.stat()
    if stat.st_size > MAX_FILE_SIZE:
        return FileReadResponse(
            error=f"文件过大 ({stat.st_size / 1024 / 1024:.1f} MB)，超过 {MAX_FILE_SIZE / 1024 / 1024:.0f} MB 限制"
        )

    mime_type, _ = mimetypes.guess_type(str(p))
    mime_type = mime_type or "text/plain"

    content = _read_file_content(p, req.start, req.end)

    return FileReadResponse(
        content=content,
        mime=mime_type,
        meta={
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "name": p.name,
        },
    )


@router.post("/open")
async def open_path(req: OpenPathRequest):
    p = Path(req.path).expanduser().resolve()
    if not is_path_permitted(str(p)):
        raise HTTPException(status_code=403, detail=f"路径未授权: {req.path}")
    if not p.exists():
        return {"ok": False, "error": f"路径不存在: {req.path}"}

    try:
        if os.name == "nt":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
        return {"ok": True, "path": str(p)}
    except Exception as e:
        logger.warning(f"[文件服务] 打开路径失败: {p} -> {e}")
        return {"ok": False, "error": str(e)}


def _list_directory(p: Path) -> FileReadResponse:
    if not p.is_dir():
        return FileReadResponse(error=f"不是目录: {p}")

    entries = []
    try:
        for item in sorted(p.iterdir()):
            if item.name.startswith("."):
                continue
            entry = {
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            }
            entries.append(entry)
    except PermissionError:
        return FileReadResponse(error=f"无权限访问目录: {p}")

    return FileReadResponse(entries=entries, meta={"path": str(p), "count": len(entries)})


def _read_file_content(p: Path, start: int | None, end: int | None) -> str:
    """读取文件内容，支持按行截取"""
    suffix = p.suffix.lower()

    if suffix == ".docx":
        return _read_docx(p)
    if suffix == ".pdf":
        return _read_pdf(p)

    raw = p.read_bytes()
    text = _decode_bytes(raw)

    if start is not None or end is not None:
        lines = text.splitlines()
        s = (start or 1) - 1
        e = end or len(lines)
        lines = lines[s:e]
        text = "\n".join(lines)

    return text


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _read_docx(p: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(p))
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        return "[错误] 需要安装 python-docx: pip install python-docx"
    except Exception as e:
        return f"[错误] 读取 docx 失败: {e}"


def _read_pdf(p: Path) -> str:
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(str(p)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        return "[错误] 需要安装 pdfplumber: pip install pdfplumber"
    except Exception as e:
        return f"[错误] 读取 PDF 失败: {e}"
