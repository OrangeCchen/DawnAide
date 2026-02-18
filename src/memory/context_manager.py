"""上下文管理器

负责从记忆系统构建 LLM 调用的上下文。
"""

from __future__ import annotations

from loguru import logger

from src.llm.base import ChatMessage
from src.memory.memory_system import MemorySystem


class ContextManager:
    """上下文管理器"""

    def __init__(self, memory: MemorySystem):
        self.memory = memory
        logger.info("上下文管理器与记忆系统已初始化")

    def build_context(
        self,
        system_prompt: str,
        user_input: str,
        partitions: list[str] | None = None,
        max_context_tokens: int = 4000,
    ) -> list[ChatMessage]:
        """构建 LLM 调用上下文

        1. system prompt
        2. 历史记忆（来自指定分区）
        3. 当前用户输入
        """
        messages = [ChatMessage(role="system", content=system_prompt)]

        # 获取历史上下文
        reserve_for_input = len(user_input) // 2 + 200
        history_budget = max_context_tokens - reserve_for_input

        history = self.memory.get_context(
            partitions=partitions,
            max_tokens=max(0, history_budget),
        )

        for entry in history:
            messages.append(ChatMessage(role=entry.role, content=entry.content))

        # 当前输入
        messages.append(ChatMessage(role="user", content=user_input))

        return messages
