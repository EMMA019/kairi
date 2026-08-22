"""AST / export map of the workspace (ported from Evo-OS StructureService).

Directory trees alone did not stop cheap models inventing function names.
This injects defined symbols and imports into the first coding turn.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

from app.core.project_context import IGNORE_DIRS
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_FILES = 40
_MAX_SYMBOLS_PER_FILE = 12
_MAX_CHARS = 1800

_CODE_SUFFIX = {".py", ".ts", ".tsx", ".js", ".jsx"}
_JS_EXPORT = re.compile(
    r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|type|interface)\s+(\w+)"
)


def _iter_code_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    stack = [root]
    seen = 0
    while stack and seen < _MAX_FILES:
        cur = stack.pop()
        try:
            entries = sorted(cur.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            continue
        for entry in entries:
            if seen >= _MAX_FILES:
                return
            if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                continue
            if entry.is_dir():
                stack.append(entry)
                continue
            if entry.suffix.lower() in _CODE_SUFFIX:
                seen += 1
                yield entry


def _analyze_python(code: str) -> tuple[list[str], list[str]]:
    tree = ast.parse(code)
    symbols: list[str] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            symbols.append(f"def {node.name}")
        elif isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    # Prefer top-level-looking names; cap length
    symbols = symbols[:_MAX_SYMBOLS_PER_FILE]
    imports = sorted(set(imports))
    return symbols, imports


def _analyze_js(code: str) -> list[str]:
    names = []
    for m in _JS_EXPORT.finditer(code or ""):
        name = m.group(1)
        if name and not name.startswith("_") and name not in names:
            names.append(name)
        if len(names) >= _MAX_SYMBOLS_PER_FILE:
            break
    return names


def analyze_workspace(workspace_dir: str, max_chars: int = _MAX_CHARS) -> str:
    """Compact symbol/import map for the executor prompt."""
    root = Path(workspace_dir)
    if not root.is_dir():
        return ""

    symbol_lines: list[str] = []
    dep_lines: list[str] = []
    for path in _iter_code_files(root):
        try:
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".py":
            try:
                symbols, imports = _analyze_python(text)
            except SyntaxError as e:
                logger.debug("structure parse skip %s: %s", rel, e)
                continue
            if symbols:
                symbol_lines.append(f"- {rel}: {', '.join(symbols)}")
            if imports:
                dep_lines.append(f"- {rel} → {', '.join(imports)}")
        else:
            names = _analyze_js(text)
            if names:
                symbol_lines.append(f"- {rel}: export {', '.join(names)}")

    if not symbol_lines and not dep_lines:
        return ""

    parts = ["【シンボル地図・Evo-OS移植】存在する関数/クラスだけを呼べ。無い名前を発明するな。"]
    if symbol_lines:
        parts.append("定義:")
        parts.extend(symbol_lines[:_MAX_FILES])
    if dep_lines:
        parts.append("import:")
        parts.extend(dep_lines[:_MAX_FILES])
    text = "\n".join(parts)
    if len(text) > max_chars:
        return text[:max_chars] + "... [中略]"
    return text
