"""联网搜索工具

基于 DuckDuckGo（ddgs 库），免费、无需 API Key。
提供文本搜索和新闻搜索两种模式。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger


@dataclass
class SearchResult:
    """单条搜索结果"""
    title: str
    url: str
    snippet: str


async def web_search(
    query: str,
    max_results: int = 5,
    region: str = "cn-zh",
) -> list[SearchResult]:
    """执行联网搜索（异步包装）

    Args:
        query: 搜索关键词
        max_results: 最大结果数
        region: 搜索区域，cn-zh 中文优先
    """
    attempts = [
        ("text", region),
        ("text", "wt-wt"),
        ("news", region),
        ("news", "wt-wt"),
    ]
    collected: list[SearchResult] = []

    for mode, reg in attempts:
        try:
            batch = await asyncio.to_thread(
                _ddg_search if mode == "text" else _ddg_news,
                query,
                max_results,
                reg,
            )
            collected = _merge_results(collected, batch, max_results)
            logger.info(f"[搜索] mode={mode} region={reg} '{query}' → +{len(batch)}")
            if len(collected) >= max_results:
                break
        except Exception as e:
            logger.warning(f"[搜索] mode={mode} region={reg} 失败: {e}")

    logger.info(f"[搜索] '{query}' 最终返回 {len(collected)} 条结果")
    return collected


async def web_search_news(
    query: str,
    max_results: int = 5,
    region: str = "cn-zh",
) -> list[SearchResult]:
    """搜索最新新闻"""
    attempts = [
        ("news", region),
        ("news", "wt-wt"),
        ("text", region),
        ("text", "wt-wt"),
    ]
    collected: list[SearchResult] = []

    for mode, reg in attempts:
        try:
            batch = await asyncio.to_thread(
                _ddg_news if mode == "news" else _ddg_search,
                query,
                max_results,
                reg,
            )
            collected = _merge_results(collected, batch, max_results)
            logger.info(f"[搜索·新闻] mode={mode} region={reg} '{query}' → +{len(batch)}")
            if len(collected) >= max_results:
                break
        except Exception as e:
            logger.warning(f"[搜索·新闻] mode={mode} region={reg} 失败: {e}")

    logger.info(f"[搜索·新闻] '{query}' 最终返回 {len(collected)} 条结果")
    return collected


def build_references(
    results: list[SearchResult],
    start_index: int = 1,
) -> list[dict]:
    """将搜索结果转为结构化引用列表"""
    refs = []
    for i, r in enumerate(results, start_index):
        refs.append({
            "id": i,
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
        })
    return refs


def format_search_results(
    results: list[SearchResult],
    query: str = "",
    references: list[dict] | None = None,
) -> str:
    """将搜索结果格式化为 LLM 可读的文本

    如果提供了 references，使用编号引用格式，方便 LLM 引用标注。
    """
    if not results:
        return f"[搜索无结果] 关键词: {query}" if query else "[搜索无结果]"

    refs = references or build_references(results)
    parts = [f"🔍 联网搜索结果（关键词: {query}，共 {len(refs)} 条）：\n"]
    for ref in refs:
        parts.append(f"[{ref['id']}] **{ref['title']}**")
        parts.append(f"    {ref['snippet']}")
        parts.append(f"    来源: {ref['url']}")
        parts.append("")
    return "\n".join(parts)


def _ddg_search(query: str, max_results: int, region: str) -> list[SearchResult]:
    """DuckDuckGo 文本搜索（同步）"""
    from ddgs import DDGS

    ddgs = DDGS(proxy=None)
    results = []
    for r in ddgs.text(query, region=region, max_results=max_results):
        results.append(SearchResult(
            title=r.get("title", ""),
            url=r.get("href", ""),
            snippet=r.get("body", ""),
        ))
    return results


def _ddg_news(query: str, max_results: int, region: str) -> list[SearchResult]:
    """DuckDuckGo 新闻搜索（同步）"""
    from ddgs import DDGS

    ddgs = DDGS(proxy=None)
    results = []
    for r in ddgs.news(query, region=region, max_results=max_results):
        results.append(SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("body", ""),
        ))
    return results


def _merge_results(
    existing: list[SearchResult],
    new_items: list[SearchResult],
    max_results: int,
) -> list[SearchResult]:
    """按 URL 去重合并搜索结果"""
    merged = list(existing)
    seen_urls = {item.url.strip() for item in merged if item.url.strip()}

    for item in new_items:
        url = (item.url or "").strip()
        if not url:
            continue
        if url in seen_urls:
            continue
        merged.append(item)
        seen_urls.add(url)
        if len(merged) >= max_results:
            break

    return merged
