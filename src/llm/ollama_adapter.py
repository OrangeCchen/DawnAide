"""Ollama 本地模型适配器"""

from __future__ import annotations

from typing import AsyncIterator

import httpx
from loguru import logger

from src.llm.base import ChatMessage, LLMAdapter, LLMResponse


class OllamaAdapter(LLMAdapter):
    """Ollama 本地模型适配器"""

    def __init__(self, base_url: str, model: str):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        logger.info(f"Ollama 适配器已创建: model={model}, base_url={base_url}")

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        resp = await self.client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=self.model,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0)
                + data.get("eval_count", 0),
            },
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with self.client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            import json

            async for line in resp.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content

    def count_tokens(self, text: str) -> int:
        return len(text) // 2
