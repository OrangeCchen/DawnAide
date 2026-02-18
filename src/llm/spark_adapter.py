"""讯飞星火大模型适配器（使用 OpenAI 兼容接口）"""

from __future__ import annotations

from typing import AsyncIterator

from loguru import logger
from openai import AsyncOpenAI

from src.llm.base import ChatMessage, LLMAdapter, LLMResponse


class SparkAdapter(LLMAdapter):
    """讯飞星火 API 适配器

    星火大模型提供了 OpenAI 兼容的 API 接口，
    因此底层复用 AsyncOpenAI 客户端。
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        model: str,
    ):
        self.model = model
        # 星火 OpenAI 兼容接口使用 api_key:api_secret 作为 key
        combined_key = f"{api_key}:{api_secret}"
        self.client = AsyncOpenAI(api_key=combined_key, base_url=base_url)
        logger.info(f"星火适配器已创建: model={model}, base_url={base_url}")

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def count_tokens(self, text: str) -> int:
        # 星火模型粗略估算
        return len(text) // 2
