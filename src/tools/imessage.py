"""iMessage 发送工具

通过 macOS Messages.app 的 AppleScript 接口发送 iMessage。
仅支持 macOS 系统，需要 Messages.app 已登录 iMessage 账号。
"""

from __future__ import annotations

import asyncio
import subprocess
import platform
from dataclasses import dataclass

from loguru import logger


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    to: str
    content: str
    error: str = ""


def _escape_applescript(text: str) -> str:
    """转义 AppleScript 字符串中的特殊字符"""
    return text.replace("\\", "\\\\").replace('"', '\\"')


async def send_imessage(to: str, message: str) -> SendResult:
    """发送 iMessage

    Args:
        to: 收件人手机号或 Apple ID 邮箱（如 +8613800138000 或 xxx@icloud.com）
        message: 消息内容

    Returns:
        SendResult 包含发送是否成功的信息
    """
    if platform.system() != "Darwin":
        return SendResult(
            success=False, to=to, content=message,
            error="iMessage 仅支持 macOS 系统",
        )

    if not to or not message:
        return SendResult(
            success=False, to=to, content=message,
            error="收件人和消息内容不能为空",
        )

    try:
        result = await asyncio.to_thread(_send_via_applescript, to, message)
        if result.success:
            logger.info(f"[iMessage] 发送成功: to={to}, len={len(message)}")
        else:
            logger.warning(f"[iMessage] 发送失败: {result.error}")
        return result
    except Exception as e:
        logger.error(f"[iMessage] 异常: {e}")
        return SendResult(success=False, to=to, content=message, error=str(e))


def _send_via_applescript(to: str, message: str) -> SendResult:
    """通过 AppleScript 发送 iMessage（同步）"""
    safe_to = _escape_applescript(to.strip())
    safe_msg = _escape_applescript(message)

    # AppleScript：通过 Messages.app 发送 iMessage
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{safe_to}" of targetService
        send "{safe_msg}" to targetBuddy
    end tell
    '''

    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if proc.returncode == 0:
            return SendResult(success=True, to=to, content=message)
        else:
            error_msg = proc.stderr.strip()
            # 常见错误友好化
            if "Can't get account" in error_msg:
                error_msg = "未找到 iMessage 账户，请确认 Messages.app 已登录 iMessage"
            elif "Can't get participant" in error_msg or "Can't get buddy" in error_msg:
                error_msg = f"未找到联系人 {to}，请确认手机号或邮箱正确"
            return SendResult(success=False, to=to, content=message, error=error_msg)
    except subprocess.TimeoutExpired:
        return SendResult(
            success=False, to=to, content=message,
            error="发送超时（15秒），请检查 Messages.app 是否正常",
        )
    except FileNotFoundError:
        return SendResult(
            success=False, to=to, content=message,
            error="未找到 osascript 命令，请确认在 macOS 系统上运行",
        )


def format_send_result(result: SendResult) -> str:
    """格式化发送结果为 LLM 可读文本"""
    if result.success:
        return (
            f"✅ iMessage 发送成功\n"
            f"收件人: {result.to}\n"
            f"消息内容: {result.content}"
        )
    else:
        return (
            f"❌ iMessage 发送失败\n"
            f"收件人: {result.to}\n"
            f"消息内容: {result.content}\n"
            f"错误原因: {result.error}"
        )
