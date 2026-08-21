"""Skip Supervisor LLM on easy chat turns (no search, no tools).

Greetings already short-circuit in chat_modes. This covers short Q&A that
would otherwise pay a full supervisor round-trip before the executor speaks.
Disable with KAIRI_SUPERVISOR_SKIP=0.
"""
from __future__ import annotations

import os
import re
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_CHARS = 400

_TOOLISH = re.compile(
    r"(?i)("
    r"\b(write|implement|fix|create|run|execute|debug|deploy|commit|refactor|"
    r"patch|install|build|compile|pytest|npm|cargo|docker)\b|"
    r"作って|実装|修正して|ファイル|実行して|書いて|デバッグ|コミット|"
    r"デプロイ|リファクタ|パッチ|インストール"
    r")"
)

_HARD = re.compile(
    r"(?i)("
    r"今日|本日|昨日|最新|速報|市況|終値|大引け|寄り|ニュース|株価|日経|ダウ|"
    r"\btoday\b|\byesterday\b|\blatest\b|\bnews\b|\bmarket\b|\bclose\b|"
    r"検索して|調べて|引用|ソース|"
    r"覚えて|記憶して|remember\b|"
    r"```|<\w+>"
    r")"
)

_PATHISH = re.compile(r"(?i)(\./|\\|[A-Za-z]:\\|\.(py|ts|tsx|go|rs|js|json|yaml|toml|md)\b)")


def supervisor_skip_enabled() -> bool:
    raw = os.environ.get("KAIRI_SUPERVISOR_SKIP", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def should_skip_supervisor(
    user_input: str,
    *,
    search_needed: bool,
    mode: str = "chat",
    force_search: bool = False,
) -> bool:
    if not supervisor_skip_enabled():
        return False
    if force_search or search_needed:
        return False
    if (mode or "chat") not in ("chat",):
        return False
    text = (user_input or "").strip()
    if not text or len(text) > _MAX_CHARS:
        return False
    if text.startswith("http://") or text.startswith("https://") or "http://" in text or "https://" in text:
        return False
    if _TOOLISH.search(text) or _HARD.search(text) or _PATHISH.search(text):
        return False
    return True


def skipped_supervisor_json() -> dict[str, Any]:
    """Minimal executor-compatible supervisor payload (no plan, no tools)."""
    return {
        "mode": "chat",
        "search_used": False,
        "silence": False,
        "needs_followup": False,
        "plan": None,
        "kv_action": {"action": "none"},
        "supervisor_skipped": True,
        "instruction": {
            "facts_to_present": [],
            "tone": "concise",
        },
    }
