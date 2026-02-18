"""本地文件读取工具

支持：
- 读取单个文件
- 读取目录下所有代码文件（递归）
- 自动过滤二进制文件和 node_modules 等
- 输出带文件名和行号的文本，方便 Agent 分析
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

# 支持的代码文件扩展名
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
    ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".m", ".mm",
    ".html", ".css", ".scss", ".less", ".sass",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".rst", ".xml", ".sql",
    ".sh", ".bash", ".zsh", ".fish",
    ".dockerfile", ".gitignore", ".env.example",
}

# 需要跳过的目录
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", ".output",
    "target", "bin", "obj", ".idea", ".vscode",
}

# 单文件大小上限（防止读入巨大文件）
MAX_FILE_SIZE = 100 * 1024  # 100KB
# 目录读取总大小上限
MAX_TOTAL_SIZE = 500 * 1024  # 500KB


def read_file(path: str) -> str:
    """读取单个文件，返回带文件路径的格式化文本"""
    p = Path(path).expanduser().resolve()

    if not p.exists():
        return f"[错误] 文件不存在: {path}"

    if not p.is_file():
        return f"[错误] 不是文件: {path}"

    if p.stat().st_size > MAX_FILE_SIZE:
        return f"[警告] 文件过大 ({p.stat().st_size} bytes)，只读取前 {MAX_FILE_SIZE} bytes\n" + _read_content(p, MAX_FILE_SIZE)

    return _read_content(p)


def read_directory(path: str, max_depth: int = 3) -> str:
    """递归读取目录下的代码文件

    返回格式：
    === 文件: path/to/file.py ===
    1| import os
    2| ...
    """
    p = Path(path).expanduser().resolve()

    if not p.exists():
        return f"[错误] 路径不存在: {path}"

    if p.is_file():
        return read_file(path)

    if not p.is_dir():
        return f"[错误] 不是有效路径: {path}"

    files = _collect_files(p, max_depth=max_depth)

    if not files:
        return f"[信息] 目录下没有找到代码文件: {path}"

    result_parts = []
    total_size = 0
    file_count = 0

    # 先输出目录结构
    result_parts.append(f"📁 目录: {p}\n找到 {len(files)} 个代码文件:\n")
    for f in files:
        rel = f.relative_to(p)
        result_parts.append(f"  - {rel}")
    result_parts.append("\n" + "=" * 60 + "\n")

    # 逐个读取文件内容
    for f in files:
        if total_size >= MAX_TOTAL_SIZE:
            result_parts.append(f"\n[截断] 已达到总大小上限 ({MAX_TOTAL_SIZE // 1024}KB)，剩余文件省略")
            break

        rel = f.relative_to(p)
        content = _read_content(f, MAX_FILE_SIZE)
        total_size += len(content.encode("utf-8", errors="replace"))
        file_count += 1

        result_parts.append(f"\n=== 文件: {rel} ===\n{content}")

    result_parts.append(f"\n--- 共读取 {file_count}/{len(files)} 个文件，总计约 {total_size // 1024}KB ---")
    return "\n".join(result_parts)


def read_paths(paths: list[str]) -> str:
    """读取多个路径（文件或目录），合并结果"""
    results = []
    for path in paths:
        path = path.strip()
        if not path:
            continue
        p = Path(path).expanduser().resolve()
        if p.is_dir():
            results.append(read_directory(path))
        else:
            results.append(f"\n=== 文件: {p.name} ({p}) ===\n{read_file(path)}")
    return "\n\n".join(results) if results else "[信息] 未提供有效路径"


def _read_content(filepath: Path, max_bytes: int | None = None) -> str:
    """安全读取文件内容"""
    try:
        raw = filepath.read_bytes()
        if max_bytes and len(raw) > max_bytes:
            raw = raw[:max_bytes]

        # 尝试 UTF-8 解码
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gbk")
            except UnicodeDecodeError:
                return f"[二进制文件，无法读取: {filepath.name}]"

        # 添加行号
        lines = text.splitlines()
        numbered = []
        for i, line in enumerate(lines, 1):
            numbered.append(f"{i:>4}| {line}")
        return "\n".join(numbered)

    except Exception as e:
        return f"[读取错误: {e}]"


def _collect_files(directory: Path, max_depth: int, current_depth: int = 0) -> list[Path]:
    """收集目录下的代码文件"""
    if current_depth > max_depth:
        return []

    files = []
    try:
        for item in sorted(directory.iterdir()):
            if item.name.startswith(".") and item.name not in (".env.example",):
                continue

            if item.is_dir():
                if item.name.lower() in SKIP_DIRS:
                    continue
                files.extend(_collect_files(item, max_depth, current_depth + 1))
            elif item.is_file():
                if item.suffix.lower() in CODE_EXTENSIONS or item.name.lower() in ("makefile", "dockerfile", "jenkinsfile"):
                    files.append(item)
    except PermissionError:
        pass

    return files
