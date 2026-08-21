"""BYOK key smoke-test. Used by first-run wizard (Gemini / Groq / DeepSeek)."""
from __future__ import annotations

import os
from typing import Any

import httpx
import openai

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _classify_openai_error(exc: BaseException) -> str:
    msg = str(exc).lower()
    status = getattr(exc, "status_code", None)
    if status is None and hasattr(exc, "response") and exc.response is not None:
        status = getattr(exc.response, "status_code", None)

    if isinstance(exc, openai.AuthenticationError) or status == 401:
        return "invalid_key"
    if status == 402 or any(
        x in msg for x in ("insufficient", "balance", "quota", "billing", "payment", "クレジット", "残高")
    ):
        return "balance"
    if isinstance(exc, openai.RateLimitError) or status == 429:
        return "rate_limit"
    if isinstance(exc, (openai.APIConnectionError, httpx.TimeoutException, httpx.ConnectError)):
        return "network"
    if "timeout" in msg or "connection" in msg or "network" in msg:
        return "network"
    return "unknown"


def _ensure_v1_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url.endswith("/v1"):
        return f"{url}/v1"
    return url


async def ping_openai_compatible_key(
    api_key: str,
    *,
    base_url: str,
    provider: str,
) -> dict[str, Any]:
    """Hit an OpenAI-compatible /v1 with models.list. Does not persist the key."""
    key = (api_key or "").strip().strip("\"'")
    if not key:
        return {"ok": False, "error": "empty", "detail": "API key is empty", "provider": provider}

    client = openai.AsyncOpenAI(
        api_key=key,
        base_url=_ensure_v1_base(base_url),
        timeout=httpx.Timeout(20.0, connect=10.0),
    )
    try:
        await client.models.list()
        return {"ok": True, "provider": provider}
    except Exception as e:
        code = _classify_openai_error(e)
        logger.warning(f"{provider} key ping failed: {code} ({e})")
        return {"ok": False, "error": code, "detail": str(e)[:300], "provider": provider}
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def ping_deepseek_key(api_key: str) -> dict[str, Any]:
    """Hit DeepSeek with a minimal authenticated call. Does not persist the key."""
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return await ping_openai_compatible_key(api_key, base_url=base_url, provider="deepseek")


async def ping_groq_key(api_key: str) -> dict[str, Any]:
    """Hit Groq (OpenAI-compatible, free tier, no card) with models.list."""
    base_url = os.environ.get("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL)
    return await ping_openai_compatible_key(api_key, base_url=base_url, provider="groq")


async def ping_gemini_key(api_key: str) -> dict[str, Any]:
    """Hit Google AI Studio with a models list call. Does not persist the key."""
    key = (api_key or "").strip().strip("\"'")
    if not key:
        return {"ok": False, "error": "empty", "detail": "API key is empty", "provider": "gemini"}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = await client.get(
                _GEMINI_MODELS_URL,
                params={"key": key, "pageSize": 1},
            )
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.warning(f"gemini key ping failed: network ({e})")
        return {"ok": False, "error": "network", "detail": str(e)[:300], "provider": "gemini"}
    except Exception as e:
        logger.warning(f"gemini key ping failed: unknown ({e})")
        return {"ok": False, "error": "unknown", "detail": str(e)[:300], "provider": "gemini"}

    if response.status_code == 200:
        return {"ok": True, "provider": "gemini"}
    body = (response.text or "")[:300]
    upper = body.upper()
    if response.status_code == 429:
        return {"ok": False, "error": "rate_limit", "detail": body, "provider": "gemini"}
    if response.status_code in (400, 401, 403) or "API_KEY_INVALID" in upper:
        return {
            "ok": False,
            "error": "invalid_key",
            "detail": body,
            "provider": "gemini",
        }
    logger.warning(f"gemini key ping failed: HTTP {response.status_code}")
    return {
        "ok": False,
        "error": "unknown",
        "detail": body or f"HTTP {response.status_code}",
        "provider": "gemini",
    }
