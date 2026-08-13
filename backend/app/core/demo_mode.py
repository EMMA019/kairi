"""Key-free demo mode (KAIRI_DEMO=1).

Shows the grounding pipeline on a fixed fixture without calling an LLM.
Intended for first-time visitors and screenshots — not a substitute for live chat.
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator


def demo_enabled() -> bool:
    return os.environ.get("KAIRI_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


_FIXTURE_RAW = (
    "Alex、おっしゃる通りです。ゼブラトン社は昨夜の引け後に70%上昇しました。"
    "お出かけ前に公式サイトでご確認ください。"
)

_FIXTURE_SOURCE = (
    "Market wrap: major indices mixed. No mention of Zebraton. "
    "No 70% move confirmed in primary sources."
)


def run_demo_grounding(user_input: str = "") -> dict[str, str]:
    """Return before/after for the canned grounding demo."""
    from app.core.fact_filters.pipeline import apply_grounding_pipeline

    after = apply_grounding_pipeline(
        _FIXTURE_RAW,
        source_text=_FIXTURE_SOURCE,
        user_input=user_input or "How did markets do?",
    )
    return {
        "raw": _FIXTURE_RAW,
        "filtered": after,
        "note": (
            "KAIRI_DEMO=1: no LLM call. This is the offline grounding pipeline "
            "on a fixed fixture (false attribution, unknown entity, numeric claim)."
        ),
    }


async def demo_chat_sse(user_input: str) -> AsyncIterator[str]:
    """Minimal SSE stream matching the chat contract: status → chunk → done."""
    result = run_demo_grounding(user_input)
    body = (
        f"{result['note']}\n\n"
        f"**Before filters**\n{result['raw']}\n\n"
        f"**After grounding pipeline**\n{result['filtered']}\n\n"
        "Set a real API key and unset KAIRI_DEMO for live chat."
    )

    def _event(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield _event({"type": "status", "content": "demo: grounding pipeline (no LLM)"})
    # Chunk in a few pieces so the UI looks like streaming
    step = max(40, len(body) // 4)
    for i in range(0, len(body), step):
        yield _event({"type": "chunk", "content": body[i : i + step]})
    # Omit content on done so the frontend keeps streamed chunks
    # (explicit "" would wipe the buffer — see useChat.ts finalContent).
    yield _event({"type": "done"})
