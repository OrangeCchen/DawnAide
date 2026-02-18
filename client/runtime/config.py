"""Client Runtime 配置"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

RUNTIME_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = str(Path.home() / ".agentteams")


class RuntimeSettings(BaseSettings):
    """Runtime 服务配置"""

    host: str = Field(default="127.0.0.1", alias="RUNTIME_HOST")
    port: int = Field(default=19800, alias="RUNTIME_PORT")
    version: str = "0.1.0"

    data_dir: str = Field(default=DEFAULT_DATA_DIR, alias="RUNTIME_DATA_DIR")

    # 向量化配置（复用主系统 embedding 或使用本地模型）
    embedding_model: str = Field(default="text-embedding-v4", alias="EMBEDDING_MODEL")
    embedding_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        alias="EMBEDDING_BASE_URL",
    )
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")

    # 分块配置
    chunk_size: int = Field(default=512, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=64, alias="CHUNK_OVERLAP")

    # 安全
    auth_token: str = Field(default="", alias="RUNTIME_AUTH_TOKEN")

    model_config = {"env_file": str(RUNTIME_DIR / ".env"), "extra": "ignore"}


_settings: RuntimeSettings | None = None


def get_settings() -> RuntimeSettings:
    global _settings
    if _settings is None:
        _settings = RuntimeSettings()
    return _settings
