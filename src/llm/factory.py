"""LLM 适配器工厂"""

from __future__ import annotations

from loguru import logger

from src.config import LLMSettings
from src.llm.base import LLMAdapter


def create_llm_adapter(settings: LLMSettings) -> LLMAdapter:
    """根据配置创建对应的 LLM 适配器"""
    provider = settings.provider

    if provider == "openai":
        from src.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    elif provider == "spark":
        from src.llm.spark_adapter import SparkAdapter

        adapter = SparkAdapter(
            api_key=settings.spark_api_key,
            api_secret=settings.spark_api_secret,
            base_url=settings.spark_base_url,
            model=settings.spark_model,
        )
    elif provider == "ollama":
        from src.llm.ollama_adapter import OllamaAdapter

        adapter = OllamaAdapter(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}")

    logger.info(f"LLM 适配器已创建: provider={provider}")
    return adapter
