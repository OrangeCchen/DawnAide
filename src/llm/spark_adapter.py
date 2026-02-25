"""讯飞星火大模型适配器（原生 WebSocket API）"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
from datetime import datetime
from time import mktime
from typing import AsyncIterator
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

import websockets
from loguru import logger

from src.llm.base import ChatMessage, LLMAdapter, LLMResponse

# 模型 domain -> WebSocket URL 映射
SPARK_DOMAIN_URL_MAP: dict[str, str] = {
    "4.0Ultra":   "wss://spark-api.xf-yun.com/v4.0/chat",
    "max-32k":    "wss://spark-api.xf-yun.com/chat/max-32k",
    "generalv3.5": "wss://spark-api.xf-yun.com/v3.5/chat",
    "pro-128k":   "wss://spark-api.xf-yun.com/chat/pro-128k",
    "generalv3":  "wss://spark-api.xf-yun.com/v3.1/chat",
    "lite":       "wss://spark-api.xf-yun.com/v1.1/chat",
    "kjwx":       "wss://spark-openapi-n.cn-huabei-1.xf-yun.com/v1.1/chat_kjwx",
}


def _build_auth_url(api_key: str, api_secret: str, spark_url: str) -> str:
    """构建带 HMAC-SHA256 鉴权参数的 WebSocket URL。

    鉴权步骤：
    1. 用 RFC1123 格式生成当前时间戳
    2. 拼接签名原文：host / date / request-line
    3. HMAC-SHA256(api_secret, 签名原文) 后 Base64 编码
    4. 将 authorization / date / host 作为 URL 查询参数追加
    """
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))

    parsed = urlparse(spark_url)
    host = parsed.netloc
    path = parsed.path

    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    params = {"authorization": authorization, "date": date, "host": host}
    return spark_url + "?" + urlencode(params)


class SparkAdapter(LLMAdapter):
    """讯飞星火大模型适配器（原生 WebSocket API）

    支持版本：
      - Spark 4.0 Ultra  (domain=4.0Ultra)
      - Spark Max-32K    (domain=max-32k)
      - Spark Max        (domain=generalv3.5)
      - Spark Pro-128K   (domain=pro-128k)
      - Spark Pro        (domain=generalv3)
      - Spark Lite       (domain=lite)
      - 科技文献大模型     (domain=kjwx)

    ``model`` 字段即为 domain 参数值。
    """

    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        model: str = "4.0Ultra",
    ):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.model = model
        logger.info(f"星火适配器已创建: domain={model}")

    def _get_auth_url(self) -> str:
        """根据当前 model(domain) 获取带鉴权参数的 WSS URL"""
        base = SPARK_DOMAIN_URL_MAP.get(self.model)
        if not base:
            raise ValueError(
                f"不支持的星火模型 domain: {self.model}，"
                f"可选值: {list(SPARK_DOMAIN_URL_MAP)}"
            )
        return _build_auth_url(self.api_key, self.api_secret, base)

    def _build_payload(
        self,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """构建 Spark API 请求 JSON 字符串"""
        text_list = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.role in ("system", "user", "assistant")
        ]
        chat_params: dict = {
            "domain": self.model,
            "temperature": round(max(0.01, min(1.0, temperature)), 2),
        }
        if max_tokens:
            chat_params["max_tokens"] = max_tokens

        return json.dumps(
            {
                "header": {"app_id": self.app_id, "uid": "user"},
                "parameter": {"chat": chat_params},
                "payload": {"message": {"text": text_list}},
            },
            ensure_ascii=False,
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> LLMResponse:
        """非流式调用：内部收集所有流式帧后一次性返回"""
        url = self._get_auth_url()
        request_str = self._build_payload(messages, temperature, max_tokens)
        ssl_ctx = ssl.create_default_context()

        full_content = ""
        usage: dict = {}

        async with websockets.connect(url, ssl=ssl_ctx) as ws:
            await ws.send(request_str)

            async for raw in ws:
                data = json.loads(raw)
                code = data["header"]["code"]
                if code != 0:
                    raise RuntimeError(
                        f"星火 API 错误 (code={code}): "
                        f"{data['header'].get('message', '未知错误')}"
                    )

                for item in data.get("payload", {}).get("choices", {}).get("text", []):
                    full_content += item.get("content", "")

                if data["header"]["status"] == 2:
                    raw_usage = (
                        data.get("payload", {}).get("usage", {}).get("text", {})
                    )
                    usage = {
                        "prompt_tokens": raw_usage.get("prompt_tokens", 0),
                        "completion_tokens": raw_usage.get("completion_tokens", 0),
                        "total_tokens": raw_usage.get("total_tokens", 0),
                    }
                    break

        return LLMResponse(content=full_content, model=self.model, usage=usage)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式调用：逐帧 yield 文本片段"""
        url = self._get_auth_url()
        request_str = self._build_payload(messages, temperature, max_tokens)
        ssl_ctx = ssl.create_default_context()

        async with websockets.connect(url, ssl=ssl_ctx) as ws:
            await ws.send(request_str)

            async for raw in ws:
                data = json.loads(raw)
                code = data["header"]["code"]
                if code != 0:
                    raise RuntimeError(
                        f"星火 API 错误 (code={code}): "
                        f"{data['header'].get('message', '未知错误')}"
                    )

                for item in data.get("payload", {}).get("choices", {}).get("text", []):
                    content = item.get("content", "")
                    if content:
                        yield content

                if data["header"]["status"] == 2:
                    break

    def count_tokens(self, text: str) -> int:
        return len(text) // 2
