"""Publish approved drafts to own Discord webhook and/or own GitHub repo issues.

Does not scrape, reply, DM, or comment on third-party posts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.core.promo.config import promo_config
from app.core.promo.store import posted_today_count, update_draft
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PublishError(RuntimeError):
    pass


async def publish_draft(draft_id: int, *, dry_run: bool = False) -> dict[str, Any]:
    from app.core.promo.store import get_draft

    cfg = promo_config()
    draft = get_draft(draft_id)
    if draft["status"] not in ("draft", "approved"):
        raise PublishError(f"cannot publish status={draft['status']}")
    cap = int(cfg.get("daily_cap") or 1)
    if posted_today_count() >= cap:
        raise PublishError(f"daily cap reached ({cap})")

    channel = draft.get("channel") or "discord"
    title = draft.get("title") or "Kairi"
    body = draft.get("body") or ""

    if dry_run:
        logger.info(f"📢 [DRY-RUN] promo #{draft_id} channel={channel} title={title[:60]}")
        return {"ok": True, "dry_run": True, "id": draft_id}

    if channel == "github":
        ok, detail = await _post_github(title, body, cfg)
    else:
        ok, detail = await _post_discord(body)

    if not ok:
        update_draft(draft_id, error=detail)
        raise PublishError(detail)

    return update_draft(
        draft_id,
        status="posted",
        error="",
        posted_at=datetime.now(timezone.utc).isoformat(),
    )


async def _post_discord(body: str) -> tuple[bool, str]:
    from app.core.notify.discord import send_discord_text

    cfg = promo_config()
    if not cfg.get("discord_webhook_set"):
        return False, "DISCORD_WEBHOOK_URL is not set"
    ok = await send_discord_text(body, dry_run=False)
    if not ok:
        return False, "discord webhook failed"
    return True, ""


async def _post_github(title: str, body: str, cfg: dict[str, Any]) -> tuple[bool, str]:
    repo = (cfg.get("github_repo") or "").strip()
    token = (cfg.get("_github_token") or "").strip()
    if not repo or "/" not in repo:
        return False, "promo_github_repo is empty (owner/name)"
    if not token:
        return False, "KAIRI_PROMO_GITHUB_TOKEN / GITHUB_TOKEN is not set"
    url = f"https://api.github.com/repos/{quote(repo, safe='/')}/issues"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kairi-promo",
    }
    payload = {
        "title": title[:250],
        "body": body,
        "labels": ["kairi-promo"],
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201):
            issue_url = (resp.json() or {}).get("html_url") or ""
            logger.info(f"✅ GitHub promo issue: {issue_url}")
            return True, issue_url
        return False, f"github {resp.status_code}: {resp.text[:300]}"
    except Exception as e:
        return False, str(e)
