"""
News Scheduler — 定期RSS巡回でローリングプールを満たす。

LLM は呼ばない。feed_health 記録と save_news のみ。
間隔は 10 分（radar の 30 分より細かく、ボード表示を鮮度良く保つ）。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

_news_task: Optional[asyncio.Task] = None
_is_running: bool = False
NEWS_INTERVAL_SECONDS = 600  # 10分
_STARTUP_DELAY_SECONDS = 20


async def run_news_ingest_once() -> dict:
    """1回分のRSS取得→プール保存。戻り値は統計。"""
    from app.core.news.database import init_db, save_news, purge_old_news, RETENTION_HOURS
    from app.core.news.fetcher import fetch_rss_on_demand
    from app.core.news.region import annotate_items_with_region

    await init_db()
    raw = await fetch_rss_on_demand()
    items = annotate_items_with_region(raw)
    inserted = await save_news(items)
    purged = await purge_old_news(RETENTION_HOURS)
    stats = {
        "fetched": len(raw),
        "inserted": inserted,
        "purged": purged,
    }
    logger.info(
        f"📰 [NewsScheduler] ingest done: fetched={stats['fetched']} "
        f"inserted={stats['inserted']} purged={stats['purged']}"
    )
    return stats


async def _news_background_loop():
    global _is_running
    _is_running = True
    logger.info(
        f"📰 [NewsScheduler] 定期RSSループ起動（インターバル: {NEWS_INTERVAL_SECONDS}秒）"
    )
    await asyncio.sleep(_STARTUP_DELAY_SECONDS)

    while _is_running:
        try:
            await run_news_ingest_once()
        except Exception as e:
            logger.error(f"❌ [NewsScheduler] ingest 例外: {e}")

        for _ in range(NEWS_INTERVAL_SECONDS):
            if not _is_running:
                break
            await asyncio.sleep(1)

    logger.info("🛑 [NewsScheduler] ループ停止")


def setup_scheduler():
    """後方互換: start_news_scheduler のエイリアス。"""
    start_news_scheduler()


def start_news_scheduler():
    global _news_task, _is_running
    if _news_task is not None and not _news_task.done():
        logger.info("⚠️ [NewsScheduler] 既に稼働中")
        return
    _is_running = True
    _news_task = asyncio.create_task(_news_background_loop())
    logger.info("🚀 [NewsScheduler] バックグラウンドタスク登録")


def shutdown_scheduler():
    stop_news_scheduler()


def stop_news_scheduler():
    global _is_running, _news_task
    _is_running = False
    if _news_task is not None:
        _news_task.cancel()
        _news_task = None
    logger.info("🛑 [NewsScheduler] 停止信号送信")
