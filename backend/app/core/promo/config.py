"""Promo flags. Env overrides settings.json when set."""
from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def promo_config() -> dict[str, Any]:
    settings: dict[str, Any] = {}
    try:
        from app.routers.settings import app_settings

        settings = app_settings.get() or {}
    except Exception:
        settings = {}

    enabled = _env_bool("KAIRI_PROMO_ENABLED")
    if enabled is None:
        enabled = bool(settings.get("promo_enabled"))

    auto_post = _env_bool("KAIRI_PROMO_AUTO_POST")
    if auto_post is None:
        auto_post = bool(settings.get("promo_auto_post"))

    discord = _env_bool("KAIRI_PROMO_DISCORD")
    if discord is None:
        discord = settings.get("promo_discord")
        discord = True if discord is None else bool(discord)

    github = _env_bool("KAIRI_PROMO_GITHUB")
    if github is None:
        github = bool(settings.get("promo_github"))

    disclose = _env_bool("KAIRI_PROMO_DISCLOSE_BOT")
    if disclose is None:
        disclose = settings.get("promo_disclose_bot")
        disclose = True if disclose is None else bool(disclose)

    cap = _env_int("KAIRI_PROMO_DAILY_CAP")
    if cap is None:
        try:
            cap = int(settings.get("promo_daily_cap") or 1)
        except (TypeError, ValueError):
            cap = 1
    cap = max(0, min(cap, 5))

    repo = (os.environ.get("KAIRI_PROMO_GITHUB_REPO") or settings.get("promo_github_repo") or "").strip()
    token = (
        os.environ.get("KAIRI_PROMO_GITHUB_TOKEN")
        or settings.get("github_token")
        or ""
    ).strip()
    webhook = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()

    return {
        "enabled": bool(enabled),
        "auto_post": bool(auto_post),
        "discord": bool(discord),
        "github": bool(github),
        "disclose_bot": bool(disclose),
        "daily_cap": cap,
        "github_repo": repo,
        "github_token_set": bool(token),
        "discord_webhook_set": bool(webhook),
        # secrets stay in-process; API responses use *_set flags
        "_github_token": token,
        "_discord_webhook": webhook,
    }
