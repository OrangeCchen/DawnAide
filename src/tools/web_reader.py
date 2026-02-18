"""网页内容读取工具

支持读取任意公开网页（包括微信公众号文章），提取正文内容。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from loguru import logger

# 正文内容大小上限（防止超长页面撑爆 token）
MAX_CONTENT_LENGTH = 8000


@dataclass
class WebPage:
    """网页读取结果"""
    url: str
    title: str
    content: str
    success: bool
    error: str = ""


async def read_url(url: str) -> WebPage:
    """异步读取网页内容

    自动识别并提取正文，过滤导航栏、广告等噪音。
    支持微信公众号文章、普通网页等。
    """
    try:
        page = await asyncio.to_thread(_fetch_and_parse, url)
        if page.success:
            logger.info(f"[网页读取] 成功: {page.title} ({len(page.content)} 字)")
        else:
            logger.warning(f"[网页读取] 失败: {page.error}")
        return page
    except Exception as e:
        logger.warning(f"[网页读取] 异常: {e}")
        return WebPage(url=url, title="", content="", success=False, error=str(e))


async def read_urls(urls: list[str]) -> list[WebPage]:
    """并行读取多个网页"""
    tasks = [read_url(url) for url in urls]
    return await asyncio.gather(*tasks)


def format_webpage(page: WebPage) -> str:
    """格式化网页内容为 LLM 可读文本"""
    if not page.success:
        return f"[网页读取失败] URL: {page.url}\n错误: {page.error}"

    content = page.content
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n...(内容过长，已截断)"

    return (
        f"📄 网页内容读取结果\n"
        f"标题: {page.title}\n"
        f"来源: {page.url}\n"
        f"正文长度: {len(page.content)} 字\n"
        f"---\n{content}"
    )


def _fetch_and_parse(url: str) -> WebPage:
    """同步：获取网页并解析正文"""
    import httpx
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    try:
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=15.0,
            verify=False,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()

            # 处理编码
            content_type = resp.headers.get("content-type", "")
            if "charset" not in content_type.lower():
                resp.encoding = resp.apparent_encoding or "utf-8"

            html = resp.text
    except httpx.HTTPStatusError as e:
        return WebPage(url=url, title="", content="", success=False,
                       error=f"HTTP {e.response.status_code}")
    except Exception as e:
        return WebPage(url=url, title="", content="", success=False,
                       error=str(e))

    soup = BeautifulSoup(html, "html.parser")

    # 提取标题
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 移除无用标签
    for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                               "aside", "iframe", "noscript", "svg"]):
        tag.decompose()

    # 针对微信公众号文章优化
    is_wechat = "mp.weixin.qq.com" in url
    content = ""

    if is_wechat:
        # 微信公众号正文在 #js_content 中
        article = soup.find(id="js_content")
        if article:
            content = _extract_text(article)
        # 尝试获取公众号文章标题
        title_el = soup.find(id="activity-name")
        if title_el:
            title = title_el.get_text(strip=True)
    else:
        # 通用网页：尝试语义标签
        article = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"(article|content|post|entry|main)", re.I))
            or soup.find(id=re.compile(r"(article|content|post|entry|main)", re.I))
        )
        if article:
            content = _extract_text(article)
        else:
            # 兜底：取 body
            body = soup.find("body")
            if body:
                content = _extract_text(body)

    if not content.strip():
        return WebPage(url=url, title=title, content="", success=False,
                       error="无法提取正文内容")

    return WebPage(url=url, title=title, content=content.strip(), success=True)


def _extract_text(element) -> str:
    """从 HTML 元素中提取干净的文本，保留基本结构"""
    lines = []
    for el in element.descendants:
        if el.name in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                        "blockquote", "tr"):
            text = el.get_text(strip=True)
            if text and len(text) > 1:
                prefix = ""
                if el.name and el.name.startswith("h"):
                    level = int(el.name[1])
                    prefix = "#" * level + " "
                elif el.name == "li":
                    prefix = "- "
                elif el.name == "blockquote":
                    prefix = "> "
                lines.append(prefix + text)

    # 去重（嵌套标签可能导致重复）
    seen = set()
    unique = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)

    return "\n\n".join(unique)
