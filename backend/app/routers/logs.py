"""違和感ログ API ルーター（種類タグ付き）"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.core.violation_log import (
    CANONICAL_VIOLATION_TYPES,
    append_violation_log,
    list_violation_logs,
    normalize_violation_type,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ViolationLogIn(BaseModel):
    session_id: str
    user_message: str
    ai_response: str
    violation_type: str
    reason: Optional[str] = None
    source: Optional[str] = "user"
    timestamp: Optional[datetime] = None

    @field_validator("violation_type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        return normalize_violation_type(v)


@router.post("/log/violation")
async def log_violation(log: ViolationLogIn):
    """違和感ログを記録（日別JSONファイルに保存）"""
    entry = append_violation_log(
        session_id=log.session_id,
        user_message=log.user_message,
        ai_response=log.ai_response,
        violation_type=log.violation_type,
        reason=log.reason,
        source=log.source or "user",
    )
    return {"success": True, "violation_type": entry["violation_type"]}


@router.get("/log/violations")
async def get_violations(date: str = None):
    """違和感ログを取得（日付指定可）"""
    resolved, logs = list_violation_logs(date)
    return {"logs": logs, "date": resolved, "canonical_types": list(CANONICAL_VIOLATION_TYPES)}
