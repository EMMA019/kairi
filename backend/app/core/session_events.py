"""
Append-only session event log (dsh-inspired: model-visible ⟺ logged).

Events are written as JSONL under storage/session_events/{session_id}.jsonl.
Anything that reaches the model or the user-facing final text should leave a trail here.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_EVENTS_DIR = Path(__file__).resolve().parents[2] / "storage" / "session_events"
SESSION_FORMAT_VERSION = 1

# Closed set of event types we currently emit
EVENT_TYPES = frozenset(
    {
        "session/open",
        "user/message",
        "assistant/message",
        "grounding/apply",
        "grounding/before",
        "grounding/after",
        "tool/call",
        "tool/result",
        "plan/proposed",
        "plan/approved",
        "plan/discarded",
        "compaction",
        "skill/catalog",
        "skill/loaded",
        "skill/catalog_refresh",
        "user/question",
        "todo/write",
        "job/start",
        "job/end",
        "prompt/static",
        "prompt/dynamic",
        "goal/change",
    }
)


def _path_for(session_id: str) -> Path:
    safe = "".join(c for c in (session_id or "unknown") if c.isalnum() or c in "-_")
    return SESSION_EVENTS_DIR / f"{safe}.jsonl"


def append_event(
    session_id: str,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    *,
    ignorable: bool = False,
) -> dict[str, Any]:
    """Append one durable event. Returns the written record."""
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown session event type %r — writing anyway", event_type)
    record = {
        "v": SESSION_FORMAT_VERSION,
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "session_id": session_id,
        "type": event_type,
        "ignorable": bool(ignorable),
        "payload": payload or {},
    }
    try:
        SESSION_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        path = _path_for(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("session_events append failed: %s", e)
    return record


def read_events(session_id: str, *, types: Optional[Iterable[str]] = None) -> list[dict]:
    """Read all events for a session (oldest first)."""
    path = _path_for(session_id)
    if not path.exists():
        return []
    allow = set(types) if types else None
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if allow is not None and rec.get("type") not in allow:
                    continue
                out.append(rec)
    except Exception as e:
        logger.warning("session_events read failed: %s", e)
    return out


def truncate_text(text: str, limit: int = 4000) -> str:
    if not text or len(text) <= limit:
        return text or ""
    half = max(200, limit // 2)
    return text[:half] + f"\n…[{len(text)} chars truncated]…\n" + text[-half:]
