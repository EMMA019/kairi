"""News health / board / briefing API"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/news/health")
async def news_health():
    """フィード健全性とローリングプール件数を返す（段階ステータス付き）。"""
    from app.core.news.database import (
        init_db,
        get_feed_health,
        count_pool,
        get_pool_news,
        RETENTION_HOURS,
    )
    from app.core.news.health_status import grade_fleet

    await init_db()
    feeds = await get_feed_health()
    pool_total = await count_pool()
    recent_18h = await get_pool_news(hours=18, limit=500)
    fleet = grade_fleet(
        feeds,
        pool_total=pool_total,
        pool_last_18h=len(recent_18h),
    )
    return {
        "pool_total": pool_total,
        "pool_last_18h": len(recent_18h),
        "retention_hours": RETENTION_HOURS,
        "feeds": fleet["feeds"],
        "feeds_failing": fleet["feeds_failing"],
        "feeds_problem": fleet["feeds_problem"],
        "status_counts": fleet["status_counts"],
        "verdict": fleet["verdict"],
        # 後方互換: 真偽値は UNHEALTHY 以外を True（監視のフラッピング抑制）
        "ok": fleet["ok"],
    }


@router.get("/news/board")
async def news_board(
    hours: float = Query(18, ge=1, le=72),
    limit: int = Query(60, ge=1, le=200),
    region: Optional[str] = Query(
        None,
        description="US | JP | EU | CN_ASIA | GLOBAL。省略時は全地域。",
    ),
):
    """News Desk 向け: 地域タグ付きのランキング済み記事ボード。"""
    from app.core.news.database import init_db, get_news_board, get_feed_health, count_pool
    from app.core.news.health_status import grade_fleet
    from app.core.news.region import REGIONS, normalize_region

    if region is not None and normalize_region(region) is None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid region; expected one of {list(REGIONS)}",
        )

    await init_db()
    board = await get_news_board(hours=hours, limit=limit, region=region)
    feeds = await get_feed_health()
    fleet = grade_fleet(
        feeds,
        pool_total=await count_pool(),
        pool_last_18h=board["pool_scanned"],
    )
    return {
        **board,
        "verdict": fleet["verdict"],
        "ok": fleet["ok"],
        "regions": list(REGIONS),
    }


@router.post("/briefing/generate")
async def generate_briefing_now(
    kind: str = Query("preopen", pattern="^(preopen|postclose)$"),
    dry_run: bool = Query(False),
):
    """手動でブリーフィング下書きを生成（目視確認用）。"""
    from app.core.briefing.generator import generate_briefing

    result = await generate_briefing(kind, dry_run=dry_run)  # type: ignore[arg-type]
    return {
        "success": True,
        "kind": result["kind"],
        "path": result["path"],
        "story_count": result["story_count"],
        "pool_count": result["pool_count"],
        "dry_run": result["dry_run"],
        "has_commentary": result.get("has_commentary", False),
        "preview": (result.get("markdown") or "")[:2000],
    }


@router.get("/briefing/list")
async def briefing_list():
    """保存済みブリーフィング一覧。"""
    from app.core.briefing.generator import list_briefing_files

    return {"files": list_briefing_files()}


@router.get("/briefing/file/{filename}")
async def briefing_file(filename: str):
    """ブリーフィング本文（パストラバーサル対策済み）。"""
    from app.core.briefing.generator import read_briefing_file

    try:
        content = read_briefing_file(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid filename")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    return {"filename": filename, "content": content}
