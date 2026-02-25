"""OpenAI 兼容 API 适配器（同时支持任何 OpenAI 兼容接口）"""

from __future__ import annotations

from typing import AsyncIterator

from httpx import Timeout
from loguru import logger
from openai import AsyncOpenAI

from src.llm.base import ChatMessage, LLMAdapter, LLMResponse

# 连接超时 10s，读取超时 120s（流式响应可能较慢），写入超时 30s
_DEFAULT_TIMEOUT = Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class OpenAIAdapter(LLMAdapter):
    """OpenAI API 适配器"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=_DEFAULT_TIMEOUT,
        )
        logger.info(f"OpenAI 适配器已创建: model={model}, base_url={base_url}")

    def _is_thinking_model(self) -> bool:
        """判断当前模型是否为 qwen3 系列（默认开启 thinking，非流式需显式关闭）"""
        return "qwen3" in self.model.lower()

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        # qwen3 系列非流式调用必须显式关闭 thinking，否则 API 返回 400
        extra_body = kwargs.pop("extra_body", None)
        if self._is_thinking_model() and extra_body is None:
            extra_body = {"enable_thinking": False}

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
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
        """使用 tiktoken 估算 token 数"""
        try:
            import tiktoken

            enc = tiktoken.encoding_for_model(self.model)
            return len(enc.encode(text))
        except Exception:
            # 粗略估算：1 token ≈ 4 字符（英文）/ 2 字符（中文）
            return len(text) // 2
