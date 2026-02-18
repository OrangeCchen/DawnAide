"""文本 Embedding 模块 - 使用 OpenAI embedding API"""

from __future__ import annotations

import requests
from loguru import logger

from src.config import get_settings


def get_embedding(text: str) -> list[float]:
    """获取单条文本的 embedding 向量

    Args:
        text: 输入文本

    Returns:
        embedding 向量列表
    """
    settings = get_settings()
    llm_cfg = settings.llm

    # 提取基础 URL（去掉末尾的 /embeddings）
    base_url = llm_cfg.embedding_base_url.rstrip('/').replace('/embeddings', '')
    url = f"{base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {llm_cfg.openai_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": llm_cfg.embedding_model,
        "input": text,
    }

    # 禁用代理，使用直接连接
    session = requests.Session()
    session.trust_env = False
    response = session.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    data = response.json()
    embedding = data["data"][0]["embedding"]

    return embedding


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """批量获取文本的 embedding 向量

    Args:
        texts: 输入文本列表

    Returns:
        embedding 向量列表
    """
    if not texts:
        return []

    settings = get_settings()
    llm_cfg = settings.llm

    # 提取基础 URL（去掉末尾的 /embeddings）
    base_url = llm_cfg.embedding_base_url.rstrip('/').replace('/embeddings', '')
    url = f"{base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {llm_cfg.openai_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": llm_cfg.embedding_model,
        "input": texts,
    }

    # 禁用代理，使用直接连接
    session = requests.Session()
    session.trust_env = False
    response = session.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    data = response.json()
    embeddings = [item["embedding"] for item in data["data"]]

    return embeddings


def truncate_text(text: str, max_length: int = 8000) -> str:
    """截断文本，避免超过模型输入限制"""
    if len(text) <= max_length:
        return text
    return text[:max_length]
