"""消息格式化 Hook"""

from __future__ import annotations

from loguru import logger


class DisplayHooks:
    """消息显示格式化钩子"""

    _hooks: list = []

    @classmethod
    def register(cls, hook_fn):
        """注册格式化 hook"""
        cls._hooks.append(hook_fn)
        return hook_fn

    @classmethod
    def apply(cls, message: dict) -> dict:
        """应用所有 hook 格式化消息"""
        for hook in cls._hooks:
            try:
                message = hook(message)
            except Exception as e:
                logger.error(f"Hook 执行失败: {e}")
        return message


def pre_print_hook(message: dict) -> dict:
    """格式化工具消息的 pre_print Hook"""
    msg_type = message.get("type", "")

    # 为任务分配消息添加格式化
    if msg_type == "task_assignment":
        task = message.get("metadata", {}).get("task", {})
        if task:
            title = task.get("title", "")
            desc = task.get("description", "")
            message["formatted_content"] = (
                f"📋 **Task Assignment** #{task.get('id', '')}\n"
                f"**{title}**\n"
                f"{desc}"
            )

    # 为任务结果消息添加格式化
    elif msg_type == "task_result":
        status = message.get("metadata", {}).get("status_label", "")
        message["formatted_content"] = message.get("content", "")
        message["status_badge"] = status

    return message


def setup_hooks():
    """注册所有 hook"""
    DisplayHooks.register(pre_print_hook)
    logger.info("已注册类级别 pre_print Hook (格式化工具消息)")
