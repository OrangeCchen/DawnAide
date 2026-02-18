"""方法论库

管理指导 Agent 工作的方法论/流程模板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.config import DATA_DIR


@dataclass
class Methodology:
    """方法论定义"""

    name: str
    display_name: str
    description: str
    steps: list[dict[str, str]] = field(default_factory=list)
    applicable_roles: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "steps": self.steps,
            "applicable_roles": self.applicable_roles,
        }


class MethodologyLibrary:
    """方法论库"""

    def __init__(self):
        self._methodologies: dict[str, Methodology] = {}

    def register(self, methodology: Methodology):
        self._methodologies[methodology.name] = methodology

    def get(self, name: str) -> Methodology | None:
        return self._methodologies.get(name)

    def list_all(self) -> list[Methodology]:
        return list(self._methodologies.values())

    @property
    def count(self) -> int:
        return len(self._methodologies)

    def load_from_directory(self, directory: Path | None = None):
        """从 YAML 文件加载方法论"""
        if directory is None:
            directory = DATA_DIR / "methodologies"

        if not directory.exists():
            logger.warning(f"方法论目录不存在: {directory}")
            return

        for file in sorted(directory.glob("*.yaml")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    method = Methodology(**data)
                    self.register(method)
            except Exception as e:
                logger.error(f"加载方法论文件失败 {file}: {e}")

        logger.info(f"方法论库已加载，共 {self.count} 个方法论")


# 全局单例
_lib: MethodologyLibrary | None = None


def get_methodology_lib() -> MethodologyLibrary:
    global _lib
    if _lib is None:
        _lib = MethodologyLibrary()
    return _lib
