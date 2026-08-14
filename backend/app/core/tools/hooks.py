"""
Tool execution hooks (dsh-inspired tools/pre-execute + tools/post-execute).

Handlers register via register_pre_execute / register_post_execute.
ToolHandler.execute_tools is wrapped once at import time from tools/__init__
or explicitly via install_hooks().
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)

PreHook = Callable[[Any, str], Awaitable[Optional[str]] | Optional[str]]
PostHook = Callable[[Any, str, str, List[dict], float], Awaitable[None] | None]

_pre_hooks: list[PreHook] = []
_post_hooks: list[PostHook] = []
_installed = False


def register_pre_execute(fn: PreHook) -> Callable[[], None]:
    """Register a pre-execute hook. Returns disposer."""
    _pre_hooks.append(fn)

    def dispose() -> None:
        if fn in _pre_hooks:
            _pre_hooks.remove(fn)

    return dispose


def register_post_execute(fn: PostHook) -> Callable[[], None]:
    """Register a post-execute hook. Returns disposer."""
    _post_hooks.append(fn)

    def dispose() -> None:
        if fn in _post_hooks:
            _post_hooks.remove(fn)

    return dispose


def clear_hooks() -> None:
    _pre_hooks.clear()
    _post_hooks.clear()


async def _run_pre(handler: Any, text: str) -> str:
    current = text
    for hook in list(_pre_hooks):
        try:
            result = hook(handler, current)
            if hasattr(result, "__await__"):
                result = await result  # type: ignore[misc]
            if isinstance(result, str):
                current = result
        except Exception as e:
            logger.warning("tool pre-execute hook failed: %s", e)
    return current


async def _run_post(
    handler: Any,
    original: str,
    updated: str,
    events: List[dict],
    elapsed: float,
) -> None:
    for hook in list(_post_hooks):
        try:
            result = hook(handler, original, updated, events, elapsed)
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        except Exception as e:
            logger.warning("tool post-execute hook failed: %s", e)


def install_hooks() -> None:
    """Wrap ToolHandler.execute_tools once. Idempotent."""
    global _installed
    if _installed:
        return
    from app.core.tools.handler import ToolHandler

    original = ToolHandler.execute_tools

    async def execute_tools_with_hooks(self, current_response: str) -> Tuple[str, List[dict]]:
        try:
            from app.core.tools.agent_tools import current_tool_session
            current_tool_session.set(getattr(self, "session_id", "") or "")
        except Exception:
            pass
        text = await _run_pre(self, current_response)
        t0 = time.perf_counter()
        updated, events = await original(self, text)
        elapsed = time.perf_counter() - t0
        await _run_post(self, text, updated, events, elapsed)
        return updated, events

    ToolHandler.execute_tools = execute_tools_with_hooks  # type: ignore[method-assign]
    _installed = True
    logger.info("Tool pre/post-execute hooks installed")


def _default_session_logging_hooks() -> None:
    """Built-in: log tool batches to session_events."""
    from app.core.session_events import append_event, truncate_text

    async def pre(handler: Any, text: str) -> None:
        sid = getattr(handler, "session_id", None)
        try:
            from app.core.tools.agent_tools import current_tool_session
            current_tool_session.set(getattr(handler, "session_id", "") or "")
        except Exception:
            pass
        if not sid:
            return
        tags = []
        for name in (
            "file",
            "replace",
            "edit",
            "run_command",
            "read_file",
            "list_dir",
            "mcp_call",
            "search",
            "search_news",
            "search_codebase",
            "grep_search",
            "escalate",
        ):
            if f"<{name}" in text:
                tags.append(name)
        if tags:
            append_event(
                sid,
                "tool/call",
                {"tags": tags, "preview": truncate_text(text, 1500)},
            )

    async def post(handler: Any, original: str, updated: str, events: list, elapsed: float) -> None:
        sid = getattr(handler, "session_id", None)
        if not sid:
            return
        results = list(getattr(handler, "tool_results", []) or [])
        append_event(
            sid,
            "tool/result",
            {
                "elapsed_sec": round(elapsed, 3),
                "result_count": len(results),
                "results_preview": [truncate_text(r, 800) for r in results[-5:]],
                "sse_event_count": len(events or []),
            },
        )

    register_pre_execute(pre)
    register_post_execute(post)
