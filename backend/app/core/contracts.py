"""Structured agent errors (ported from KAGRA contracts.py).

Opaque FileNotFoundError made cheap models invent paths. Errors here carry
a machine code, a hint, and nearby candidate files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.project_context import IGNORE_DIRS


@dataclass
class KairiContractError(Exception):
    code: str
    message: str
    hint: str = ""
    path: str | None = None
    candidates: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.path:
            parts.append(f"path={self.path}")
        if self.candidates:
            parts.append("tried=" + ", ".join(self.candidates[:8]))
        if self.hint:
            parts.append(f"hint={self.hint}")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "path": self.path,
            "candidates": self.candidates,
        }


def format_contract(
    code: str,
    message: str,
    *,
    hint: str = "",
    path: str | None = None,
    candidates: list[str] | None = None,
) -> str:
    return str(
        KairiContractError(
            code=code,
            message=message,
            hint=hint,
            path=path,
            candidates=list(candidates or []),
        )
    )


def suggest_workspace_paths(workspace_dir: str | Path, query: str, limit: int = 6) -> list[str]:
    """Nearby files that share the basename or suffix of the missing path."""
    root = Path(workspace_dir)
    if not root.is_dir():
        return []
    needle = Path(str(query or "").replace("\\", "/")).name.lower()
    if not needle or needle in {".", "/"}:
        return []
    stem = Path(needle).stem.lower()
    hits: list[str] = []
    stack = [root]
    scanned = 0
    while stack and scanned < 400 and len(hits) < limit:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue
        for entry in entries:
            scanned += 1
            if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                continue
            if entry.is_dir():
                stack.append(entry)
                continue
            name = entry.name.lower()
            if name == needle or (stem and stem in name):
                try:
                    hits.append(entry.relative_to(root).as_posix())
                except ValueError:
                    continue
            if len(hits) >= limit:
                break
    return hits


def missing_workspace_file(
    workspace_dir: str | Path,
    raw_path: str,
    action: str = "read",
) -> str:
    cands = suggest_workspace_paths(workspace_dir, raw_path)
    if action == "edit":
        hint = (
            "近いパスを <read_file> してから <edit> するか、"
            "無いなら <file> で新規作成せよ。"
        )
    elif action == "replace":
        hint = "SEARCH対象が無い。候補を <read_file> して正確なパスで <replace> せよ。"
    else:
        hint = "候補を <read_file> するか、<list_dir> で確認せよ。パスを発明するな。"
    return format_contract(
        "WORKSPACE_NOT_FOUND",
        f"ファイルが見つかりません ({raw_path})",
        hint=hint,
        path=raw_path,
        candidates=cands,
    )
