"""本地知识库工具

对接 LocalClientAdapter，为 Agent 提供本地知识库检索能力。
Runtime 不可用时自动降级，不影响主流程。
"""

from __future__ import annotations

from loguru import logger

from src.tools.local_client_adapter import get_local_client_adapter


async def local_kb_search(
    query: str,
    collection: str = "default",
    top_k: int = 5,
) -> str:
    """检索本地知识库，返回格式化文本供 Agent 使用"""
    adapter = get_local_client_adapter()

    status = await adapter.check_health()
    if not status.online:
        return "[本地知识库] 客户端 Runtime 未运行，本地检索不可用。请确认 AgentTeams Client 已启动。"

    if "kb" not in status.capabilities:
        return "[本地知识库] 客户端 Runtime 不支持知识库能力。"

    result = await adapter.search_kb(query=query, collection=collection, top_k=top_k)
    if result is None:
        return "[本地知识库] 检索请求失败，请稍后重试。"

    hits = result.get("hits", [])
    if not hits:
        return f"[本地知识库] 未找到与「{query}」相关的内容。"

    parts = [f"📚 本地知识库检索结果（关键词: {query}，共 {len(hits)} 条）：\n"]
    for i, hit in enumerate(hits, 1):
        source = hit.get("source", "未知来源")
        content = hit.get("content", "")
        score = hit.get("score", 0)
        parts.append(f"[{i}] 来源: {source} (相关度: {score:.2f})")
        parts.append(f"    {content[:500]}")
        parts.append("")

    return "\n".join(parts)


async def local_kb_index(
    paths: list[str],
    collection: str = "default",
    reindex: bool = False,
) -> str:
    """提交本地目录索引任务"""
    adapter = get_local_client_adapter()

    status = await adapter.check_health()
    if not status.online:
        return "[本地知识库] 客户端 Runtime 未运行，无法执行索引任务。"

    result = await adapter.index_kb(paths=paths, collection=collection, reindex=reindex)
    if result is None:
        return "[本地知识库] 索引请求失败。"

    task_id = result.get("task_id", "unknown")
    return f"[本地知识库] 索引任务已提交（ID: {task_id}），正在后台处理中。"
