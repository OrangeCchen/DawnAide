"""全局配置模块"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class LLMSettings(BaseSettings):
    """LLM 相关配置"""

    provider: Literal["openai", "spark", "ollama"] = Field(
        default="openai", alias="LLM_PROVIDER"
    )

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")

    # Embedding 向量生成
    embedding_model: str = Field(default="text-embedding-v4", alias="EMBEDDING_MODEL")
    embedding_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings", alias="EMBEDDING_BASE_URL")

    # 核查专家模型（留空则自动选择与主模型不同的模型）
    reviewer_model: str = Field(default="", alias="REVIEWER_MODEL")

    # 讯飞星火
    spark_app_id: str = Field(default="", alias="SPARK_APP_ID")
    spark_api_key: str = Field(default="", alias="SPARK_API_KEY")
    spark_api_secret: str = Field(default="", alias="SPARK_API_SECRET")
    spark_model: str = Field(default="generalv3.5", alias="SPARK_MODEL")
    spark_base_url: str = Field(
        default="https://spark-api-open.xf-yun.com/v1", alias="SPARK_BASE_URL"
    )

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:14b", alias="OLLAMA_MODEL")

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


class ServerSettings(BaseSettings):
    """服务器配置"""

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


class QdrantSettings(BaseSettings):
    """Qdrant 向量数据库配置"""
    host: str = Field(default="localhost", alias="QDRANT_HOST")
    port: int = Field(default=6333, alias="QDRANT_PORT")
    api_key: str = Field(default="", alias="QDRANT_API_KEY")
    collection_name: str = Field(default="knowledge_base", alias="QDRANT_COLLECTION")
    use_https: bool = Field(default=False, alias="QDRANT_HTTPS")

    # 本地文件存储路径
    storage_path: str = Field(default="data/kb_files", alias="KB_STORAGE_PATH")

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


class TTSettings(BaseSettings):
    """TTS 语音合成配置"""
    # 讯飞 TTS
    spark_app_id: str = Field(default="", alias="SPARK_TTS_APP_ID")
    spark_api_key: str = Field(default="", alias="SPARK_TTS_API_KEY")
    spark_api_secret: str = Field(default="", alias="SPARK_TTS_API_SECRET")
    spark_ttsvoice: str = Field(default="xiaoyan", alias="SPARK_TTS_VOICE")  # 讯飞语音主播

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


class MemorySettings(BaseSettings):
    """记忆系统配置"""

    user_budget: int = 1000
    session_budget: int = 1000
    task_budget: int = 1000
    agent_budget: int = 2000

    @property
    def budgets(self) -> dict[str, int]:
        return {
            "user": self.user_budget,
            "session": self.session_budget,
            "task": self.task_budget,
            "agent": self.agent_budget,
        }


class AppSettings(BaseSettings):
    """应用总配置"""

    llm: LLMSettings = Field(default_factory=LLMSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    tts: TTSettings = Field(default_factory=TTSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)

    model_config = {"env_file": str(ROOT_DIR / ".env"), "extra": "ignore"}


# 全局单例
_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings
