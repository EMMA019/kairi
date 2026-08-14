"""
Scripted mock LLM for keyless assembled snapshots.

Mock only at the model boundary: fixed chunks. Real loop + grounding + SSE remain.
"""
from __future__ import annotations

from typing import AsyncGenerator, Optional


def chunk_text(text: str, size: int = 48) -> list[str]:
    t = text or ""
    if not t:
        return [""]
    return [t[i : i + size] for i in range(0, len(t), size)]


def make_scripted_run_executor(script: str, *, chunk_size: int = 48):
    """Return an async run_executor replacement that yields fixed chunks."""

    chunks = chunk_text(script, chunk_size)

    async def run_executor(*args, **kwargs) -> AsyncGenerator[str, None]:
        for c in chunks:
            yield c

    return run_executor


async def run_assembled_loop_snapshot(
    *,
    user_input: str,
    mock_executor_output: str,
    search_results: Optional[str] = None,
    session_id: str = "assembled-snapshot",
    instruction: str = "Answer from the provided facts only.",
) -> dict:
    """
    Real auto_execute_with_retry + grounding waterfall, fake model only.

    Returns {final_text, sse_events, session_events}.
    """
    from unittest.mock import patch

    from app.core.auto_execution_loop import auto_execute_with_retry
    from app.core.session_events import read_events, SESSION_EVENTS_DIR

    sse_events: list[dict] = []

    def yield_sse(data: dict) -> None:
        sse_events.append(dict(data))

    scripted = make_scripted_run_executor(mock_executor_output)

    # Isolate session event files under default storage; caller may monkeypatch dir.
    with patch(
        "app.core.auto_execution_loop.loop.run_executor",
        new=scripted,
    ):
        final_text, _tools, _esc = await auto_execute_with_retry(
            user_input=user_input,
            instruction=instruction,
            supervisor_sys_prompt="You are a test supervisor.",
            supervisor_dynamic_sys="",
            executor_sys_prompt="You are a test executor.",
            executor_dynamic_sys="",
            mode="chat",
            session_id=session_id,
            history_messages=[],
            search_results=search_results or "",
            memory_text=None,
            max_tool_loops=3,
            max_supervisor_retries=1,
            yield_sse_func=yield_sse,
        )

    events = read_events(session_id)
    return {
        "final_text": final_text,
        "sse_events": sse_events,
        "session_events": events,
        "session_events_dir": str(SESSION_EVENTS_DIR),
    }
