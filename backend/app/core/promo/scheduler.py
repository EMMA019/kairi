"""Daily promo collect (+ optional Discord auto-post). Own channels only."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.promo.config import promo_config
from app.utils.logger import get_logger

logger = get_logger(__name__)

JST = timezone(timedelta(hours=9))

_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


def _seconds_until(hour: int, minute: int, now: Optional[datetime] = None) -> float:
    now = now or datetime.now(JST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def run_daily_promo_once() -> dict:
    """Collect a draft; auto-post Discord only when enabled and approved-path is auto."""
    from app.core.promo.queue import enqueue_from_telemetry, maybe_autopost_discord

    created = enqueue_from_telemetry()
    posted = None
    cfg = promo_config()
    if cfg.get("enabled") and cfg.get("auto_post") and cfg.get("discord"):
        posted = await maybe_autopost_discord(created)
    return {"created": created, "posted": posted}


async def _promo_loop():
    logger.info("📣 [PromoScheduler] JST 21:00 ループ起動")
    while not _stop.is_set():
        wait_s = _seconds_until(21, 0)
        logger.info(f"📣 [PromoScheduler] next collect in {wait_s / 60:.1f} min")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=wait_s)
            break
        except asyncio.TimeoutError:
            pass
        if _stop.is_set():
            break
        try:
            if not promo_config().get("enabled"):
                logger.info("📣 [PromoScheduler] skipped (promo_enabled=0)")
            else:
                result = await run_daily_promo_once()
                logger.info(f"📣 [PromoScheduler] {result}")
        except Exception as e:
            logger.error(f"❌ [PromoScheduler] {e}")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=61)
            break
        except asyncio.TimeoutError:
            pass
    logger.info("🛑 [PromoScheduler] 停止しました")


def start_promo_scheduler():
    global _task
    if _task and not _task.done():
        logger.info("⚠️ [PromoScheduler] 既に稼働中")
        return
    if not promo_config().get("enabled"):
        logger.info("📣 [PromoScheduler] disabled (set KAIRI_PROMO_ENABLED=1)")
        return
    _stop.clear()
    _task = asyncio.create_task(_promo_loop())
    logger.info("🚀 [PromoScheduler] バックグラウンドタスク登録")


def stop_promo_scheduler():
    global _task
    _stop.set()
    if _task and not _task.done():
        _task.cancel()
    _task = None
    logger.info("🛑 [PromoScheduler] 停止信号送信")
