"""角色注册表

管理所有可用的专家角色定义。
支持从 YAML 加载和动态写入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.config import DATA_DIR


@dataclass
class RoleDefinition:
    """角色定义"""

    name: str
    display_name: str
    label: str  # Lead / Explorer / Plan / Assistant
    description: str
    system_prompt: str
    skills: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "label": self.label,
            "description": self.description,
            "skills": self.skills,
        }


class RoleRegistry:
    """角色注册表"""

    def __init__(self):
        self._roles: dict[str, RoleDefinition] = {}

    def register(self, role: RoleDefinition):
        """注册角色"""
        self._roles[role.name] = role

    def get(self, name: str) -> RoleDefinition | None:
        return self._roles.get(name)

    def list_roles(self) -> list[RoleDefinition]:
        return list(self._roles.values())

    @property
    def count(self) -> int:
        return len(self._roles)

    def load_from_directory(self, directory: Path | None = None):
        """从 YAML 文件加载角色定义"""
        if directory is None:
            directory = DATA_DIR / "roles"

        if not directory.exists():
            logger.warning(f"角色目录不存在: {directory}")
            return

        for file in sorted(directory.glob("*.yaml")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    role = RoleDefinition(**data)
                    self.register(role)
            except Exception as e:
                logger.error(f"加载角色文件失败 {file}: {e}")

        logger.info(f"专家角色库已加载，共 {self.count} 个角色")

    def save_role(self, role: RoleDefinition, directory: Path | None = None):
        """将角色定义持久化到 YAML 文件"""
        if directory is None:
            directory = DATA_DIR / "roles"

        directory.mkdir(parents=True, exist_ok=True)

        # 文件名使用角色名（替换特殊字符）
        filename = role.name.replace("-", "_").replace(" ", "_") + ".yaml"
        filepath = directory / filename

        data = {
            "name": role.name,
            "display_name": role.display_name,
            "label": role.label,
            "description": role.description,
            "system_prompt": role.system_prompt,
            "skills": role.skills,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"角色已保存: {filepath}")


# 全局单例
_registry: RoleRegistry | None = None


def get_role_registry() -> RoleRegistry:
    global _registry
    if _registry is None:
        _registry = RoleRegistry()
    return _registry
