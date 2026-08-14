"""Agent-facing tools: ask_user_question, todo_write (dsh-inspired)."""
from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Optional

from app.core.tools.registry import tool_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)

current_tool_session: ContextVar[str] = ContextVar("current_tool_session", default="")

_pending_by_session: dict[str, dict[str, Any]] = {}
_todos: dict[str, list[dict[str, str]]] = {}
_pending: Optional[dict[str, Any]] = None  # latest (handler-readable)

ALLOWED_TODO_STATUS = frozenset({"pending", "in_progress", "completed"})
ALLOW_PARALLEL_IN_PROGRESS = False


def _session_id(explicit: str = "") -> str:
    sid = (explicit or "").strip() or current_tool_session.get() or "latest"
    return sid


def pop_pending_user_question(session_id: str = "") -> Optional[dict[str, Any]]:
    """Return and clear pending question for SSE emission (or None)."""
    global _pending
    sid = _session_id(session_id)
    payload = _pending_by_session.pop(sid, None)
    if payload is None and sid != "latest":
        payload = _pending_by_session.pop("latest", None)
    if _pending is not None and (payload is None or _pending is payload):
        _pending = None
    return payload


def get_pending_user_question(session_id: str = "") -> Optional[dict[str, Any]]:
    sid = _session_id(session_id)
    return _pending_by_session.get(sid) or _pending_by_session.get("latest") or _pending


def _format_questions_md(questions: list[dict]) -> str:
    lines = ["## ユーザーへの確認質問", ""]
    for q in questions:
        qid = q.get("id") or "?"
        header = (q.get("header") or "").strip()
        title = (q.get("question") or "").strip()
        if header:
            lines.append(f"### {header}")
        lines.append(f"**[{qid}]** {title}")
        opts = q.get("options") or []
        if opts:
            multi = " (複数選択可)" if q.get("multi_select") else ""
            lines.append(f"選択肢{multi}:")
            for opt in opts:
                if isinstance(opt, dict):
                    lab = opt.get("label") or ""
                    desc = opt.get("description") or ""
                    lines.append(f"- **{lab}**" + (f" — {desc}" if desc else ""))
                else:
                    lines.append(f"- {opt}")
        lines.append("")
    lines.append(
        "（次のユーザー発話で回答が届きます。質問への回答を待ってから続行してください。）"
    )
    return "\n".join(lines)


@tool_registry.register(
    name="ask_user_question",
    description=(
        "ユーザーに構造化質問を出す。"
        "questions_json は [{id, question, header?, options?:[{label,description}], multi_select?}] の JSON 配列。"
    ),
)
def ask_user_question(questions_json: str, session_id: str = "") -> str:
    global _pending
    try:
        raw = json.loads(questions_json)
    except Exception as e:
        return f"[ERROR] questions_json が不正な JSON です: {e}"
    if not isinstance(raw, list) or not raw:
        return "[ERROR] questions_json は非空の JSON 配列である必要があります"
    questions: list[dict] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"[ERROR] questions[{i}] はオブジェクトである必要があります"
        q = (item.get("question") or "").strip()
        if not q:
            return f"[ERROR] questions[{i}].question が空です"
        qid = str(item.get("id") or f"q{i+1}")
        entry: dict[str, Any] = {"id": qid, "question": q}
        if item.get("header"):
            entry["header"] = str(item["header"])
        if item.get("options"):
            entry["options"] = item["options"]
        if item.get("multi_select"):
            entry["multi_select"] = bool(item["multi_select"])
        questions.append(entry)

    sid = _session_id(session_id)
    payload = {"session_id": sid, "questions": questions}
    _pending_by_session[sid] = payload
    _pending_by_session["latest"] = payload
    _pending = payload

    try:
        from app.core.session_events import append_event

        append_event(sid, "user/question", payload)
    except Exception as e:
        logger.warning("ask_user_question event failed: %s", e)

    md = _format_questions_md(questions)
    return md


@tool_registry.register(
    name="todo_write",
    description=(
        "TODO リストを全置換する。"
        "todos_json は [{content, status}]。status は pending|in_progress|completed。"
        "同時に in_progress は最大1件。"
    ),
)
def todo_write(todos_json: str, session_id: str = "") -> str:
    try:
        raw = json.loads(todos_json)
    except Exception as e:
        return f"[ERROR] todos_json が不正な JSON です: {e}"
    if not isinstance(raw, list):
        return "[ERROR] todos_json は JSON 配列である必要があります"

    todos: list[dict[str, str]] = []
    in_progress = 0
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"[ERROR] todos[{i}] はオブジェクトである必要があります"
        content = (item.get("content") or "").strip()
        if not content:
            return f"[ERROR] todos[{i}].content が空です"
        status = (item.get("status") or "pending").strip()
        if status not in ALLOWED_TODO_STATUS:
            return f"[ERROR] todos[{i}].status が不正です: {status}"
        if status == "in_progress":
            in_progress += 1
        todos.append({"content": content, "status": status})

    if not ALLOW_PARALLEL_IN_PROGRESS and in_progress > 1:
        return "[ERROR] in_progress は同時に1件までです (allowParallelInProgress=False)"

    sid = _session_id(session_id)
    _todos[sid] = todos

    try:
        from app.core.session_events import append_event

        append_event(
            sid,
            "todo/write",
            {
                "count": len(todos),
                "pending": sum(1 for t in todos if t["status"] == "pending"),
                "in_progress": sum(1 for t in todos if t["status"] == "in_progress"),
                "completed": sum(1 for t in todos if t["status"] == "completed"),
            },
        )
    except Exception as e:
        logger.warning("todo/write event failed: %s", e)

    counts = {
        "pending": sum(1 for t in todos if t["status"] == "pending"),
        "in_progress": sum(1 for t in todos if t["status"] == "in_progress"),
        "completed": sum(1 for t in todos if t["status"] == "completed"),
    }
    return (
        f"TODO 更新: 全{len(todos)}件 "
        f"(pending={counts['pending']}, in_progress={counts['in_progress']}, "
        f"completed={counts['completed']})"
    )


@tool_registry.register(
    name="todo_list",
    description="現在セッションの TODO リストを返す",
)
def todo_list(session_id: str = "") -> str:
    sid = _session_id(session_id)
    todos = _todos.get(sid) or []
    if not todos:
        return "TODO は空です。"
    lines = [f"TODO ({len(todos)}件):"]
    for i, t in enumerate(todos, 1):
        lines.append(f"{i}. [{t['status']}] {t['content']}")
    return "\n".join(lines)
