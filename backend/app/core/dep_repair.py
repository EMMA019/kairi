"""ModuleNotFound → requirements hint (ported from Evo-OS agent_core).

Does not silently pip-install. Appends to an existing requirements.txt and
tells the executor to run the install itself.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_MISSING = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | {
    "os",
    "sys",
    "json",
    "re",
    "pathlib",
    "typing",
    "asyncio",
    "unittest",
}

_PIP_ALIAS = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
}


def extract_missing_module(log: str) -> str | None:
    m = _MISSING.search(log or "")
    if not m:
        return None
    name = (m.group(1) or "").split(".")[0].strip()
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return None
    if name in _STDLIB:
        return None
    return name


def pip_package_name(mod: str) -> str:
    return _PIP_ALIAS.get(mod, mod)


def _is_local_module(workspace: Path, mod: str) -> bool:
    return (workspace / f"{mod}.py").is_file() or (workspace / mod / "__init__.py").is_file()


def _find_requirements(workspace: Path) -> Path | None:
    direct = workspace / "requirements.txt"
    if direct.is_file():
        return direct
    try:
        for child in workspace.iterdir():
            if child.is_dir() and (child / "requirements.txt").is_file():
                return child / "requirements.txt"
    except OSError:
        return None
    return None


def append_requirement(workspace: Path, pkg: str) -> Path | None:
    req = _find_requirements(workspace)
    if req is None:
        return None
    try:
        text = req.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = {ln.strip().split("==")[0].split(">=")[0].lower() for ln in text.splitlines() if ln.strip()}
    if pkg.lower() in lines:
        return req
    sep = "" if text.endswith("\n") or not text else "\n"
    try:
        req.write_text(text + f"{sep}{pkg}\n", encoding="utf-8")
    except OSError:
        return None
    try:
        from app.core.workspace_store import persist_workspace_file

        persist_workspace_file(req.relative_to(workspace).as_posix(), req.read_text(encoding="utf-8"))
    except Exception:
        pass
    return req


def missing_module_repair(workspace_dir: str | Path, log: str) -> str | None:
    """Return a structured tool note, or None if this is not a missing-module error."""
    if "ModuleNotFoundError" not in (log or "") and "No module named" not in (log or ""):
        return None
    mod = extract_missing_module(log)
    if not mod:
        return None
    root = Path(workspace_dir)
    if _is_local_module(root, mod):
        return (
            f"[MODULE_NOT_FOUND] ローカルモジュール `{mod}` はある。"
            " import パスか sys.path を直せ。pip するな。"
        )
    pkg = pip_package_name(mod)
    wrote = append_requirement(root, pkg)
    where = wrote.as_posix() if wrote else "requirements.txt（まだ無い。作ってよい）"
    return (
        f"[MODULE_NOT_FOUND] `{mod}` が無い。パッケージは `{pkg}`。"
        f" {where} に追記済みまたは追記せよ。"
        f" 次に <run_command>pip install {pkg}</run_command> を自分で実行しろ。"
        " ユーザーにインストールを頼むな。"
    )
