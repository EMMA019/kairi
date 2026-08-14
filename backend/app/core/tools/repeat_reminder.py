"""dsh-inspired repeat-tool-reminder: advisory only, never blocks."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

THRESHOLDS = (3, 5, 8)
EXCLUDE = frozenset({"todo_write", "job_list", "job_output", "list_tools", "list_skills"})

_chains: dict[str, dict[str, Any]] = defaultdict(lambda: {"key": None, "count": 0})


def reset_chain(session_id: str) -> None:
    if session_id in _chains:
        _chains[session_id] = {"key": None, "count": 0}


def _canon_args(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s.replace("'", '"'))
        return json.dumps(obj, sort_keys=True, ensure_ascii=False)
    except Exception:
        return re.sub(r"\s+", " ", s)[:500]


def _extract_calls(text: str) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    if not text:
        return calls
    for m in re.finditer(
        r"<(mcp_call)\s+tool=([\"'])([^\"']+)\2([^>]*)/?>",
        text,
        re.I,
    ):
        name = m.group(3)
        attrs = m.group(4) or ""
        args = ""
        am = re.search(r"args=([\"'])(.*?)\1", attrs)
        if am:
            args = am.group(2)
        else:
            parts = re.findall(r"([a-zA-Z_]+)=([\"'])(.*?)\2", attrs)
            if parts:
                args = json.dumps({k: v for k, _, v in parts}, sort_keys=True, ensure_ascii=False)
        calls.append((name, _canon_args(args)))
    for tag in ("run_command", "search", "search_news", "read_file", "list_dir", "search_codebase"):
        for m in re.finditer(rf"<{tag}\b([^>]*)>([\s\S]*?)</{tag}>", text, re.I):
            body = (m.group(2) or "").strip()
            attrs = m.group(1) or ""
            calls.append((tag, _canon_args(body or attrs)))
        for m in re.finditer(rf"<{tag}\b([^>]*)/>", text, re.I):
            calls.append((tag, _canon_args(m.group(1) or "")))
    for tag in ("file", "replace", "edit"):
        for m in re.finditer(rf"<{tag}\s+path=([\"'])([^\"']+)\1", text, re.I):
            calls.append((tag, _canon_args(m.group(2))))
    return calls


def _reminder(tool: str, count: int, args_preview: str) -> str:
    if count <= THRESHOLDS[0]:
        return (
            "【システム助言・反復検知】同じツール呼び出しが続いています。"
            "直前の結果を読み直し、方針を変えるか、回答をまとめてください。"
        )
    preview = (args_preview or "")[:200]
    return (
        f"【システム助言・反復検知】`{tool}` を同一引数で {count} 回連続呼び出しました。"
        f"引数プレビュー: {preview!r}\n"
        "同じ呼び出しの繰り返しを止め、結果を使って結論を出すか別アプローチに切り替えてください。"
    )


def observe_and_maybe_remind(session_id: str, text: str, handler: Any) -> str | None:
    if not session_id:
        return None
    calls = _extract_calls(text)
    if not calls:
        return None
    chain = _chains[session_id]
    reminder = None
    for name, args in calls:
        if name in EXCLUDE:
            continue
        key = f"{name}|{args}"
        if chain["key"] == key:
            chain["count"] += 1
        else:
            chain["key"] = key
            chain["count"] = 1
        if chain["count"] in THRESHOLDS:
            reminder = _reminder(name, chain["count"], args)
            logger.info("repeat-tool-reminder: %s x%d", name, chain["count"])
    if reminder and handler is not None:
        results = getattr(handler, "tool_results", None)
        if isinstance(results, list):
            results.append(reminder)
    return reminder


def install_repeat_reminder_hook() -> None:
    from app.core.tools.hooks import register_post_execute

    async def post(handler, original, updated, events, elapsed):
        sid = getattr(handler, "session_id", "") or ""
        observe_and_maybe_remind(sid, original or "", handler)

    register_post_execute(post)
