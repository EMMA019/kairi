"""Queue helpers: collect telemetry → drafts, optional Discord auto-post."""
from __future__ import annotations

import json
from typing import Any, Optional

from app.core.promo.collector import collect_telemetry, fingerprint_for
from app.core.promo.config import promo_config
from app.core.promo.store import (
    find_recent_fingerprint,
    insert_draft,
    list_drafts,
    posted_today_count,
)
from app.core.promo.writer import draft_from_metrics
from app.utils.logger import get_logger

logger = get_logger(__name__)


def enqueue_from_telemetry(*, locale: str | None = None) -> dict[str, Any]:
    cfg = promo_config()
    metrics = collect_telemetry()
    fp = fingerprint_for(metrics)
    existing = find_recent_fingerprint(fp, days=7)
    if existing and existing.get("status") in ("draft", "approved", "posted"):
        return {"duplicate": True, "draft": existing, "fingerprint": fp}

    loc = locale
    if not loc:
        try:
            from app.routers.settings import app_settings

            loc = app_settings.get().get("locale") or "en"
        except Exception:
            loc = "en"

    copy = draft_from_metrics(metrics, disclose_bot=bool(cfg.get("disclose_bot")), locale=str(loc))
    metrics_json = json.dumps(metrics, ensure_ascii=False)
    created: list[dict[str, Any]] = []

    channels: list[str] = []
    if cfg.get("discord"):
        channels.append("discord")
    if cfg.get("github") and cfg.get("github_repo"):
        channels.append("github")
    if not channels:
        channels = ["discord"]

    for channel in channels:
        row = insert_draft(
            channel=channel,
            title=copy["title"],
            body=copy["body"],
            fingerprint=fp,
            metrics_json=metrics_json,
        )
        created.append(row)
        logger.info(f"📣 promo draft #{row['id']} channel={channel} fp={fp}")

    return {"duplicate": False, "drafts": created, "fingerprint": fp, "metrics": metrics}


async def maybe_autopost_discord(enqueue_result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Auto-post is Discord-only. GitHub always waits for human approve."""
    cfg = promo_config()
    if not cfg.get("auto_post") or not cfg.get("discord"):
        return None
    if posted_today_count() >= int(cfg.get("daily_cap") or 1):
        logger.info("📣 promo auto-post skipped (daily cap)")
        return None

    from app.core.promo.publisher import PublishError, publish_draft

    candidates = enqueue_result.get("drafts") or []
    if enqueue_result.get("duplicate"):
        d = enqueue_result.get("draft") or {}
        if d.get("channel") == "discord" and d.get("status") in ("draft", "approved"):
            candidates = [d]
    for d in candidates:
        if d.get("channel") != "discord":
            continue
        if d.get("status") not in ("draft", "approved"):
            continue
        try:
            return await publish_draft(int(d["id"]))
        except PublishError as e:
            logger.warning(f"promo auto-post failed: {e}")
            return {"ok": False, "error": str(e)}
    return None


def public_status() -> dict[str, Any]:
    cfg = promo_config()
    drafts = list_drafts(limit=20)
    return {
        "enabled": cfg["enabled"],
        "auto_post": cfg["auto_post"],
        "discord": cfg["discord"],
        "github": cfg["github"],
        "disclose_bot": cfg["disclose_bot"],
        "daily_cap": cfg["daily_cap"],
        "github_repo": cfg["github_repo"],
        "github_token_set": cfg["github_token_set"],
        "discord_webhook_set": cfg["discord_webhook_set"],
        "posted_today": posted_today_count(),
        "draft_count": sum(1 for d in drafts if d.get("status") == "draft"),
    }
