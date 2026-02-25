"""本地文件整理执行器（安全版）

设计原则：
- 仅允许创建子目录与移动文件
- 严禁删除文件
- 提供整理前后校验，降低误操作风险
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import shutil
import re


@dataclass
class OrganizeReport:
    """文件整理执行结果"""

    root_dir: str
    total_files: int = 0
    moved_files: int = 0
    created_dirs: list[str] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    collisions: int = 0
    verify_ok: bool = False
    verify_note: str = ""

    def to_dict(self) -> dict:
        return {
            "root_dir": self.root_dir,
            "total_files": self.total_files,
            "moved_files": self.moved_files,
            "created_dirs": self.created_dirs,
            "category_counts": self.category_counts,
            "collisions": self.collisions,
            "verify_ok": self.verify_ok,
            "verify_note": self.verify_note,
        }


@dataclass
class OrganizePlan:
    """文件整理预览方案"""

    root_dir: str
    total_files: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)
    sample_moves: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "root_dir": self.root_dir,
            "total_files": self.total_files,
            "category_counts": self.category_counts,
            "sample_moves": self.sample_moves,
        }


_EXT_CATEGORY_MAP: dict[str, str] = {
    ".pdf": "文档资料",
    ".doc": "文档资料",
    ".docx": "文档资料",
    ".txt": "文档资料",
    ".md": "文档资料",
    ".rtf": "文档资料",
    ".ppt": "演示材料",
    ".pptx": "演示材料",
    ".key": "演示材料",
    ".xls": "表格数据",
    ".xlsx": "表格数据",
    ".csv": "表格数据",
    ".json": "数据文件",
    ".xml": "数据文件",
    ".yaml": "数据文件",
    ".yml": "数据文件",
    ".py": "代码文件",
    ".js": "代码文件",
    ".ts": "代码文件",
    ".tsx": "代码文件",
    ".java": "代码文件",
    ".go": "代码文件",
    ".rs": "代码文件",
    ".cpp": "代码文件",
    ".c": "代码文件",
    ".h": "代码文件",
    ".hpp": "代码文件",
    ".swift": "代码文件",
    ".png": "图片素材",
    ".jpg": "图片素材",
    ".jpeg": "图片素材",
    ".gif": "图片素材",
    ".webp": "图片素材",
    ".svg": "图片素材",
    ".zip": "压缩包",
    ".rar": "压缩包",
    ".7z": "压缩包",
    ".tar": "压缩包",
    ".gz": "压缩包",
    ".mp3": "音视频",
    ".wav": "音视频",
    ".m4a": "音视频",
    ".mp4": "音视频",
    ".mov": "音视频",
    ".avi": "音视频",
}


def organize_directory_safe(root_dir: str, organize_goal: str = "") -> OrganizeReport:
    """执行目录整理（只建目录+移动，不删除）"""
    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"目录不存在或不可访问: {root}")

    report = OrganizeReport(root_dir=str(root))
    before_count, before_size = _count_files_and_size(root)

    # 仅整理根目录下的普通文件，避免对已有子目录做深层重排
    root_files = [p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")]
    report.total_files = len(root_files)

    for src in root_files:
        category = _classify_file(src, organize_goal)
        target_dir = root / category
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            report.created_dirs.append(str(target_dir))

        target_path, has_collision = _next_available_path(target_dir / src.name)
        if has_collision:
            report.collisions += 1

        shutil.move(str(src), str(target_path))
        report.moved_files += 1
        report.category_counts[category] = report.category_counts.get(category, 0) + 1

    after_count, after_size = _count_files_and_size(root)
    report.verify_ok = (before_count == after_count and before_size == after_size)
    if report.verify_ok:
        report.verify_note = "校验通过：文件数量和总大小一致，未发生删除。"
    else:
        report.verify_note = (
            "校验异常：整理前后文件统计不一致，请使用操作日志进行人工核对。"
        )
    return report


def preview_organize_plan(root_dir: str, organize_goal: str = "", sample_limit: int = 20) -> OrganizePlan:
    """预览整理方案（不修改文件系统）"""
    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"目录不存在或不可访问: {root}")

    plan = OrganizePlan(root_dir=str(root))
    root_files = [p for p in root.iterdir() if p.is_file() and not p.name.startswith(".")]
    plan.total_files = len(root_files)
    for src in root_files:
        category = _classify_file(src, organize_goal)
        plan.category_counts[category] = plan.category_counts.get(category, 0) + 1
        if len(plan.sample_moves) < sample_limit:
            plan.sample_moves.append(
                {
                    "source": str(src),
                    "target": str((root / category / src.name)),
                }
            )
    return plan


def _classify_file(path: Path, organize_goal: str) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    goal = (organize_goal or "").lower()

    # 当用户目标包含“时间”时，按修改时间分组（YYYY-MM）
    if "时间" in organize_goal or "日期" in organize_goal or "month" in goal:
        dt = datetime.fromtimestamp(path.stat().st_mtime)
        return f"{dt.year}-{dt.month:02d}"

    # 当用户目标包含“按主题”时，优先用文件名关键词粗分
    if "主题" in organize_goal or "内容" in organize_goal:
        keyword_category = _keyword_category(name)
        if keyword_category:
            return keyword_category

    if ext in _EXT_CATEGORY_MAP:
        return _EXT_CATEGORY_MAP[ext]
    return "其他文件"


def _keyword_category(filename: str) -> str:
    mapping: list[tuple[str, str]] = [
        (r"(ai|智能体|agent|llm|大模型)", "AI相关"),
        (r"(报告|方案|总结|白皮书|文档)", "报告文档"),
        (r"(合同|发票|财务|预算|报销)", "商务财务"),
        (r"(会议|通知|纪要|日程)", "会议沟通"),
        (r"(代码|源码|repo|project)", "代码工程"),
    ]
    for pattern, category in mapping:
        if re.search(pattern, filename):
            return category
    return ""


def _next_available_path(target_path: Path) -> tuple[Path, bool]:
    if not target_path.exists():
        return target_path, False

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate, True
        index += 1


def _count_files_and_size(root: Path) -> tuple[int, int]:
    count = 0
    total_size = 0
    for p in root.rglob("*"):
        if p.is_file():
            count += 1
            try:
                total_size += p.stat().st_size
            except OSError:
                pass
    return count, total_size
