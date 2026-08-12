"""
Executor stream parsing: hold CoT until <<<FINAL_ANSWER>>>, hide tool/think tags from SSE.
"""
from __future__ import annotations

import re
from typing import Any, AsyncIterator, Callable, Optional

TOOL_TAG_NAMES = (
    r"file|replace|edit|run_command|read_url|read_file|list_dir|search|search_news|"
    r"search_codebase|grep_search|view_file|mcp_call|escalate"
)

TOOL_TAG_START = re.compile(rf"<({TOOL_TAG_NAMES})(?:\s|>|/>)")
SELF_CLOSING = re.compile(rf"<({TOOL_TAG_NAMES})[^>]*/>", re.DOTALL)
CLOSING_TAG = re.compile(rf"</({TOOL_TAG_NAMES})>", re.DOTALL)


async def iter_executor_stream(
    original_stream: AsyncIterator[str],
    yield_sse_func: Optional[Callable[[dict], Any]] = None,
) -> AsyncIterator[str]:
    """
    Yield raw chunks for internal tool detection while gating user-visible SSE
    until <<<FINAL_ANSWER>>> (or flush held text at end for legacy/tool-only turns).
    """
    from app.core.fact_filters.markup import FINAL_ANSWER_MARKER

    tag_buf = ""
    in_tag = False
    in_think_block = False
    sse_hold = ""
    fa_released = False
    _tool_or_think_prefix = re.compile(
        rf"^</?(?:think|{TOOL_TAG_NAMES})",
        re.IGNORECASE,
    )
    _partial_prefix = re.compile(
        r"^</?(?:t(?:h(?:i(?:n(?:k)?)?)?)?|"
        r"m(?:c(?:p(?:_(?:c(?:a(?:l(?:l)?)?)?)?)?)?)?|"
        r"f(?:i(?:l(?:e)?)?)?|search|read_|run_|list_|view_|grep_|escalat)",
        re.IGNORECASE,
    )

    def _emit_user(text: str) -> None:
        nonlocal sse_hold, fa_released
        if not text or in_think_block:
            return
        if not yield_sse_func:
            return
        if fa_released:
            yield_sse_func({"type": "chunk", "content": text})
            return
        sse_hold += text
        idx = sse_hold.find(FINAL_ANSWER_MARKER)
        if idx >= 0:
            fa_released = True
            after = sse_hold[idx + len(FINAL_ANSWER_MARKER) :]
            sse_hold = ""
            if after:
                yield_sse_func({"type": "chunk", "content": after})

    async for c in original_stream:
        if in_tag:
            tag_buf += c
            if ">" not in tag_buf and "\n" not in tag_buf and len(tag_buf) < 80:
                continue

            match_think = re.search(r"<think\b[^>]*>", tag_buf, re.IGNORECASE)
            match_end_think = re.search(r"</think\s*>", tag_buf, re.IGNORECASE)

            if match_think:
                before_think = tag_buf[: match_think.start()]
                if before_think and not in_think_block:
                    _emit_user(before_think)
                    yield before_think
                in_think_block = True
                tag_buf = tag_buf[match_think.end() :]
                in_tag = "<" in tag_buf
                if not in_tag:
                    tag_buf = ""
                continue

            if match_end_think:
                in_think_block = False
                tag_buf = tag_buf[match_end_think.end() :]
                in_tag = "<" in tag_buf
                if tag_buf and not in_tag:
                    _emit_user(tag_buf)
                    yield tag_buf
                    tag_buf = ""
                continue

            tool_match = re.search(rf"<({TOOL_TAG_NAMES})\b", tag_buf, re.IGNORECASE)
            if tool_match:
                if tool_match.start() > 0 and not in_think_block:
                    before_tool = tag_buf[: tool_match.start()]
                    _emit_user(before_tool)
                    yield before_tool
                yield tag_buf
                tag_buf = ""
                in_tag = False
                continue

            if _tool_or_think_prefix.search(tag_buf) or _partial_prefix.search(tag_buf):
                if "\n" in tag_buf or len(tag_buf) >= 80:
                    yield tag_buf
                    tag_buf = ""
                    in_tag = False
                continue

            if not in_think_block:
                _emit_user(tag_buf)
                yield tag_buf
            tag_buf = ""
            in_tag = False
            continue

        if "<" in c:
            idx = c.find("<")
            before_lt = c[:idx]
            if before_lt and not in_think_block:
                _emit_user(before_lt)
                yield before_lt
            in_tag = True
            tag_buf = c[idx:]
            continue
        if not in_think_block:
            _emit_user(c)
            yield c

    if tag_buf:
        if in_tag and (
            _tool_or_think_prefix.search(tag_buf)
            or _partial_prefix.search(tag_buf)
            or re.search(rf"<({TOOL_TAG_NAMES})", tag_buf, re.IGNORECASE)
        ):
            yield tag_buf
        elif not in_think_block:
            _emit_user(tag_buf)
            yield tag_buf
    if not fa_released and sse_hold and yield_sse_func:
        yield_sse_func({"type": "chunk", "content": sse_hold})
        sse_hold = ""
    yield "\n"
