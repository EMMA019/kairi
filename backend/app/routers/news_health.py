"""News health / briefing API"""
from fastapi import APIRouter, Query
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/news/health")
async def news_health():
    """フィード健全性とローリングプール件数を返す。"""
    from app.core.news.database import (
        init_db,
        get_feed_health,
        count_pool,
        get_pool_news,
        RETENTION_HOURS,
    )

    await init_db()
    feeds = await get_feed_health()
    pool_total = await count_pool()
    recent_18h = await get_pool_news(hours=18, limit=500)
    failing = [f for f in feeds if (f.get("consecutive_failures") or 0) >= 3]
    return {
        "pool_total": pool_total,
        "pool_last_18h": len(recent_18h),
        "retention_hours": RETENTION_HOURS,
        "feeds": feeds,
        "feeds_failing": len(failing),
        "ok": len(failing) == 0 or pool_total > 0,
    }


@router.post("/briefing/generate")
async def generate_briefing_now(
    kind: str = Query("preopen", pattern="^(preopen|postclose)$"),
    dry_run: bool = Query(False),
):
    """手動でブリーフィング下書きを生成（目視確認用）。"""
    from app.core.briefing.generator import generate_briefing

    result = await generate_briefing(kind, dry_run=dry_run)  # type: ignore[arg-type]
    # レスポンスに全文を載せると重いので path と件数を中心に
    return {
        "success": True,
        "kind": result["kind"],
        "path": result["path"],
        "story_count": result["story_count"],
        "pool_count": result["pool_count"],
        "dry_run": result["dry_run"],
        "preview": (result.get("markdown") or "")[:2000],
    }
