"""Free-tier LLM providers (Gemini / Groq) — no live network."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import llm_client
from app.core.key_ping import ping_gemini_key, ping_groq_key
from app.routers import settings as settings_mod
from app.routers.settings import AVAILABLE_PROVIDERS, FREE_TIER_DEFAULTS, PingKeyRequest, ping_key


def test_available_providers_include_free_tiers():
    assert "gemini" in AVAILABLE_PROVIDERS
    assert "groq" in AVAILABLE_PROVIDERS
    assert "local" in AVAILABLE_PROVIDERS
    assert FREE_TIER_DEFAULTS["gemini"]["executor_model"] == "gemini-2.5-flash"
    assert FREE_TIER_DEFAULTS["groq"]["executor_provider"] == "groq"
    assert FREE_TIER_DEFAULTS["local"]["executor_provider"] == "local"


def test_groq_key_is_masked():
    pub = settings_mod._public_settings(
        {**settings_mod._DEFAULT_SETTINGS, "groq_api_key": "gsk-secret-real"}
    )
    assert pub["groq_api_key"] == settings_mod._SECRET_MASK
    assert pub["groq_api_key_set"] is True
    assert "gsk-secret" not in str(pub)


def test_ping_gemini_and_groq_empty():
    gem = asyncio.run(ping_gemini_key("  "))
    groq = asyncio.run(ping_groq_key(""))
    assert gem["ok"] is False and gem["error"] == "empty"
    assert groq["ok"] is False and groq["error"] == "empty"


def test_ping_gemini_invalid_key(monkeypatch):
    class FakeResp:
        status_code = 400
        text = '{"error":{"status":"INVALID_ARGUMENT","message":"API_KEY_INVALID"}}'

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr("app.core.key_ping.httpx.AsyncClient", lambda **kwargs: FakeClient())
    out = asyncio.run(ping_gemini_key("AIza-bad"))
    assert out["ok"] is False
    assert out["error"] == "invalid_key"
    assert out["provider"] == "gemini"


def test_ping_local_ok_without_key():
    out = asyncio.run(ping_key(PingKeyRequest(provider="local", api_key="")))
    assert out["ok"] is True
    assert out["provider"] == "local"


def test_get_groq_client_requires_env(monkeypatch):
    llm_client.reset_llm_clients()
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        llm_client.get_groq_client()


def test_free_models_do_not_burn_daily_budget(tmp_path, monkeypatch):
    import app.core.usage_tracker as ut

    monkeypatch.setattr(ut, "DB_PATH", tmp_path / "usage.db")
    ut._init_db()
    ut.record_usage("llama-3.3-70b-versatile", 2_000_000, 2_000_000)
    ut.record_usage("gemini-2.5-flash", 2_000_000, 2_000_000)
    ut.record_usage("llama3", 2_000_000, 2_000_000)
    usage = ut.get_daily_usage()
    assert usage["total_cost_usd"] == 0.0
    assert ut.check_budget() is True
