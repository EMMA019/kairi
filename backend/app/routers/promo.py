"""Promo approval API — drafts stay local until a human posts."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.promo.collector import collect_telemetry
from app.core.promo.queue import enqueue_from_telemetry, public_status
from app.core.promo.store import get_draft, list_drafts, update_draft
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class DraftPatch(BaseModel):
    body: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None


@router.get("/promo/status")
async def promo_status():
    return public_status()


@router.get("/promo/metrics")
async def promo_metrics():
    return collect_telemetry()


@router.get("/promo/drafts")
async def promo_list(status: Optional[str] = None, limit: int = 50):
    return {"drafts": list_drafts(status=status, limit=limit)}


@router.post("/promo/collect")
async def promo_collect():
    return enqueue_from_telemetry()


@router.patch("/promo/drafts/{draft_id}")
async def promo_patch(draft_id: int, req: DraftPatch):
    try:
        row = update_draft(
            draft_id,
            body=req.body,
            title=req.title,
            status=req.status,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="draft not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return row


@router.post("/promo/drafts/{draft_id}/approve")
async def promo_approve(draft_id: int):
    try:
        return update_draft(draft_id, status="approved")
    except KeyError:
        raise HTTPException(status_code=404, detail="draft not found")


@router.post("/promo/drafts/{draft_id}/reject")
async def promo_reject(draft_id: int):
    try:
        return update_draft(draft_id, status="rejected")
    except KeyError:
        raise HTTPException(status_code=404, detail="draft not found")


@router.post("/promo/drafts/{draft_id}/post")
async def promo_post(draft_id: int):
    from app.core.promo.publisher import PublishError, publish_draft

    try:
        get_draft(draft_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="draft not found")
    try:
        return await publish_draft(draft_id)
    except PublishError as e:
        raise HTTPException(status_code=400, detail=str(e))
