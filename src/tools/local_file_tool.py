"""本地文件操作工具（通过 Client Runtime）

与现有 file_reader.py 的区别：
- file_reader.py 直接在后端进程内读取（适合后端本机文件）
- 本模块通过 Client Runtime 远程读取（适合用户桌面端本地文件）

两者独立运作，互不影响。
"""

from __future__ import annotations

from loguru import logger

from src.tools.local_client_adapter import get_local_client_adapter


async def remote_read_file(path: str) -> str:
    """通过 Client Runtime 读取用户本地文件"""
    adapter = get_local_client_adapter()

    status = await adapter.check_health()
    if not status.online:
        return (
            "[本地文件] 客户端 Runtime 未运行，无法读取本地文件。"
            "请确认 AgentTeams Client 已启动。"
        )

    result = await adapter.read_file(path=path)
    if result is None:
        return f"[本地文件] 读取失败: {path}"

    if result.get("error"):
        return f"[本地文件] {result['error']}"

    content = result.get("content", "")
    mime = result.get("mime", "text/plain")
    meta = result.get("meta", {})
    size = meta.get("size", 0)

    header = f"📄 文件: {path}\n类型: {mime} | 大小: {_format_size(size)}\n"
    return header + "─" * 40 + "\n" + content


async def remote_list_directory(path: str) -> str:
    """通过 Client Runtime 列出目录内容"""
    adapter = get_local_client_adapter()

    status = await adapter.check_health()
    if not status.online:
        return "[本地文件] 客户端 Runtime 未运行。"

    result = await adapter.read_file(path=path, mode="list")
    if result is None:
        return f"[本地文件] 目录读取失败: {path}"

    entries = result.get("entries", [])
    if not entries:
        return f"[本地文件] 目录为空: {path}"

    parts = [f"📁 目录: {path}（共 {len(entries)} 项）\n"]
    for entry in entries:
        icon = "📁" if entry.get("is_dir") else "📄"
        name = entry.get("name", "")
        size = _format_size(entry.get("size", 0))
        parts.append(f"  {icon} {name}  ({size})")

    return "\n".join(parts)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
