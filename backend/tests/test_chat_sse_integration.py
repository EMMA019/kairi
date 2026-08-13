"""
Minimal /api/chat SSE integration test.

Mocks LLM/search/executor so CI never calls providers, then asserts the
router still emits the status → chunk → done contract.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _parse_sse(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def _fake_plan_search(user_input, messages, session_id=None):
    return {
        "needs_search": False,
        "search_queries": [],
        "category": "general",
        "providers": [],
        "recommended_mode": None,
    }


async def _fake_supervisor(**kwargs):
    return (
        {
            "mode": "chat",
            "instruction": {
                "facts_to_present": ["2+2 equals 4."],
                "tone": "concise",
            },
            "search_used": False,
            "silence": False,
            "needs_followup": False,
            "kv_action": {"action": "none"},
        },
        "ok to answer directly",
    )


async def _fake_auto_execute(**kwargs):
    yield_sse = kwargs.get("yield_sse_func")
    text = "2+2 equals 4."
    if yield_sse:
        yield_sse({"type": "chunk", "content": text})
    return text, "", []


def test_chat_sse_chunk_then_done():
    from app.main import app

    with patch(
        "app.core.search_planner.plan_search",
        new=AsyncMock(side_effect=_fake_plan_search),
    ), patch(
        "app.core.supervisor.run_supervisor",
        new=AsyncMock(side_effect=_fake_supervisor),
    ), patch(
        "app.core.auto_execution_loop.auto_execute_with_retry",
        new=AsyncMock(side_effect=_fake_auto_execute),
    ), patch(
        "app.routers.chat.get_llm_cache",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.routers.chat.set_llm_cache",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.core.chat_modes.check_greeting_short_circuit",
        return_value=None,
    ), patch(
        "app.routers.chat._save_messages",
        new=AsyncMock(return_value=None),
    ), patch(
        "app.routers.chat._get_conversation_messages",
        new=AsyncMock(return_value=[]),
    ), patch(
        # Local settings may have a token; open the door for this contract test.
        "app.core.auth._configured_token",
        return_value="",
    ):
        client = TestClient(app)
        res = client.post(
            "/api/chat",
            json={
                "message": "What is 2+2? answer briefly",
                "session_id": "sse-integration-test",
                "mode": "chat",
            },
        )

    assert res.status_code == 200, res.text
    assert "text/event-stream" in (res.headers.get("content-type") or "")

    events = _parse_sse(res.text)
    types = [e.get("type") for e in events]

    assert "status" in types
    assert "chunk" in types
    assert "done" in types
    assert "error" not in types

    chunks = "".join(e.get("content", "") for e in events if e.get("type") == "chunk")
    assert "4" in chunks

    done = next(e for e in events if e.get("type") == "done")
    assert done.get("ok") is True
    assert "4" in (done.get("content") or "")
    # done comes after at least one chunk
    assert types.index("chunk") < types.index("done")
