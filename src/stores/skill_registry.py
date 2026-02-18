"""技能注册表

管理所有可用的 Agent 技能，支持基于触发条件自动判断启用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.config import DATA_DIR


@dataclass
class SkillDefinition:
    """技能定义

    trigger 格式:
      type: always             — 始终启用
      type: task_metadata      — 当 task.metadata[key] 为真时启用
        key: file_paths
      type: expert_flag        — 当任意专家的 flag 为真时启用
        key: needs_search
    """

    name: str
    display_name: str
    category: str  # builtin / tool / ...
    description: str
    icon: str = ""
    trigger: dict[str, str] = field(default_factory=dict)
    prompt_template: str = ""
    parameters: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """带图标的显示标签，如 '🔍 联网搜索'"""
        if self.icon:
            return f"{self.icon} {self.display_name}"
        return self.display_name

    def is_active(
        self,
        task_metadata: dict | None = None,
        experts: list[dict] | None = None,
    ) -> bool:
        """根据触发条件判断当前技能是否应该激活"""
        trigger_type = self.trigger.get("type", "")

        if trigger_type == "always":
            return True

        if trigger_type == "task_metadata":
            key = self.trigger.get("key", "")
            if task_metadata and key:
                return bool(task_metadata.get(key))
            return False

        if trigger_type == "expert_flag":
            key = self.trigger.get("key", "")
            if experts and key:
                return any(e.get(key) for e in experts)
            return False

        return False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "icon": self.icon,
            "category": self.category,
            "description": self.description,
            "trigger": self.trigger,
            "parameters": self.parameters,
        }


class SkillRegistry:
    """技能注册表"""

    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition):
        """注册技能"""
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def list_skills(self, category: str | None = None) -> list[SkillDefinition]:
        if category:
            return [s for s in self._skills.values() if s.category == category]
        return list(self._skills.values())

    @property
    def count(self) -> int:
        return len(self._skills)

    def resolve_active_skills(
        self,
        task_metadata: dict | None = None,
        experts: list[dict] | None = None,
    ) -> list[SkillDefinition]:
        """根据上下文返回所有应该激活的技能（保持注册顺序）"""
        return [
            s for s in self._skills.values()
            if s.is_active(task_metadata=task_metadata, experts=experts)
        ]

    def resolve_active_labels(
        self,
        task_metadata: dict | None = None,
        experts: list[dict] | None = None,
    ) -> list[str]:
        """返回应该激活的技能标签列表，如 ['🕐 时间感知', '🔍 联网搜索']"""
        return [s.label for s in self.resolve_active_skills(task_metadata, experts)]

    def load_from_directory(self, directory: Path | None = None):
        """从 YAML 文件加载技能定义"""
        if directory is None:
            directory = DATA_DIR / "skills"

        if not directory.exists():
            logger.warning(f"技能目录不存在: {directory}")
            return

        for file in sorted(directory.glob("*.yaml")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    for item in data:
                        skill = SkillDefinition(**item)
                        self.register(skill)
                elif data:
                    skill = SkillDefinition(**data)
                    self.register(skill)
            except Exception as e:
                logger.error(f"加载技能文件失败 {file}: {e}")

        logger.info(f"技能注册表已加载，共 {self.count} 个技能")


# 全局单例
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
