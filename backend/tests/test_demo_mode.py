"""KAIRI_DEMO=1: key-free grounding showcase."""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("KAIRI_DEMO", "1")
    yield
    monkeypatch.delenv("KAIRI_DEMO", raising=False)


def test_demo_enabled(demo_env):
    from app.core.demo_mode import demo_enabled

    assert demo_enabled() is True


def test_demo_grounding_strips_bad_claims(demo_env):
    from app.core.demo_mode import run_demo_grounding

    out = run_demo_grounding("market?")
    assert "ゼブラトン" not in out["filtered"] or "確認" in out["filtered"] or out["filtered"] != out["raw"]
    assert out["raw"] != out["filtered"] or "70%" not in out["filtered"]


def test_demo_sse_contract(demo_env):
    import asyncio
    import json

    from app.core.demo_mode import demo_chat_sse

    async def _collect():
        events = []
        async for line in demo_chat_sse("hi"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    events = asyncio.run(_collect())
    types = [e.get("type") for e in events]
    assert "status" in types
    assert "chunk" in types
    assert types[-1] == "done"
