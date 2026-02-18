"""场景模板注册表

管理预定义的使用场景（如公文写作、调研分析等）。
每个场景包含信息收集字段和 prompt 模板，由前端渲染为卡片入口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.config import DATA_DIR


@dataclass
class SceneField:
    """场景表单字段"""

    id: str
    label: str
    type: str = "text"  # text / select / multiselect
    placeholder: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)


@dataclass
class SceneTemplate:
    """场景子模板（如"会议通知""工作总结"）"""

    id: str
    name: str
    description: str = ""
    fields: list[dict[str, Any]] = field(default_factory=list)
    prompt_template: str = ""

    def render_prompt(self, form_data: dict[str, str]) -> str:
        """将表单数据填入 prompt_template"""
        result = self.prompt_template
        for key, value in form_data.items():
            result = result.replace(f"{{{key}}}", value or "（未填写）")
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "fields": self.fields,
        }


@dataclass
class SceneCategory:
    """场景分类（如"公文写作""日常写作"）"""

    name: str
    display_name: str
    icon: str = ""
    description: str = ""
    methodology: str = ""
    children: list[dict[str, Any]] = field(default_factory=list)

    def get_template(self, template_id: str) -> SceneTemplate | None:
        for child in self.children:
            if child.get("id") == template_id:
                return SceneTemplate(**child)
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "icon": self.icon,
            "description": self.description,
            "methodology": self.methodology,
            "children": [
                {
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "fields": c.get("fields", []),
                }
                for c in self.children
            ],
        }


class SceneRegistry:
    """场景注册表"""

    def __init__(self):
        self._categories: dict[str, SceneCategory] = {}

    def register(self, category: SceneCategory):
        self._categories[category.name] = category

    def get(self, name: str) -> SceneCategory | None:
        return self._categories.get(name)

    def get_template(self, category_name: str, template_id: str) -> SceneTemplate | None:
        cat = self.get(category_name)
        if cat:
            return cat.get_template(template_id)
        return None

    def list_categories(self) -> list[SceneCategory]:
        return list(self._categories.values())

    @property
    def count(self) -> int:
        return len(self._categories)

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self._categories.values()]

    def load_from_directory(self, directory: Path | None = None):
        if directory is None:
            directory = DATA_DIR / "scenes"

        if not directory.exists():
            logger.warning(f"场景目录不存在: {directory}")
            return

        for file in sorted(directory.glob("*.yaml")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    category = SceneCategory(**data)
                    self.register(category)
            except Exception as e:
                logger.error(f"加载场景文件失败 {file}: {e}")

        logger.info(f"场景注册表已加载，共 {self.count} 个场景分类")


_registry: SceneRegistry | None = None


def get_scene_registry() -> SceneRegistry:
    global _registry
    if _registry is None:
        _registry = SceneRegistry()
    return _registry
