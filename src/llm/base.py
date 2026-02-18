"""LLM 适配器抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ChatMessage:
    """聊天消息"""

    role: str  # "system" | "user" | "assistant"
    content: str
    name: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class LLMResponse:
    """LLM 响应"""

    content: str
    model: str = ""
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens


class LLMAdapter(ABC):
    """LLM 适配器抽象接口

    所有 LLM provider 都需要实现此接口。
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """同步聊天（返回完整响应）"""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式聊天（逐 token 返回）"""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """估算文本的 token 数量"""
        ...
