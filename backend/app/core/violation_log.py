"""違和感ログの永続化（ユーザー報告・supervisor 自動検出の共通先）"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

VIOLATION_LOG_DIR = Path(__file__).resolve().parents[2] / "storage" / "violation_logs"

# フロント英語ラベル ↔ 内部正規ラベル
VIOLATION_TYPE_ALIASES: dict[str, str] = {
    "Unsolicited Proposal": "先回り提案",
    "Unauthorized Memory": "KV無断記憶",
    "Repeated Questions": "質問の連投",
    "Excessive Praise": "過剰な称賛",
    "Search Skipped": "検索スキップ",
    "Thought Leakage": "思考漏れ出し",
    "Other": "その他",
    "先回り提案": "先回り提案",
    "KV無断記憶": "KV無断記憶",
    "質問の連投": "質問の連投",
    "過剰な称賛": "過剰な称賛",
    "検索スキップ": "検索スキップ",
    "思考漏れ出し": "思考漏れ出し",
    "その他": "その他",
}

CANONICAL_VIOLATION_TYPES = (
    "先回り提案",
    "KV無断記憶",
    "質問の連投",
    "過剰な称賛",
    "検索スキップ",
    "思考漏れ出し",
    "その他",
)


def normalize_violation_type(raw: str | None) -> str:
    if not raw:
        return "その他"
    key = str(raw).strip()
    return VIOLATION_TYPE_ALIASES.get(key, "その他")


def append_violation_log(
    *,
    session_id: str,
    user_message: str,
    ai_response: str,
    violation_type: str,
    reason: Optional[str] = None,
    source: str = "user",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """日別 JSON に1件追記して返す。"""
    VIOLATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = VIOLATION_LOG_DIR / f"{today}.json"

    existing: list[dict[str, Any]] = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = []

    entry: dict[str, Any] = {
        "session_id": session_id or "",
        "user_message": user_message or "",
        "ai_response": ai_response or "",
        "violation_type": normalize_violation_type(violation_type),
        "reason": reason,
        "source": source if source in ("user", "supervisor") else "user",
        "timestamp": datetime.now().isoformat(),
    }
    if extra:
        entry["extra"] = extra

    existing.append(entry)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    logger.info(
        f"違和感ログ記録: type={entry['violation_type']} source={entry['source']}"
    )
    return entry


def list_violation_logs(date: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    log_file = VIOLATION_LOG_DIR / f"{date}.json"
    if not log_file.exists():
        return date, []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
        if isinstance(logs, list):
            return date, logs
    except (json.JSONDecodeError, OSError):
        pass
    return date, []


def iter_all_violation_logs() -> list[dict[str, Any]]:
    """全日付のログを新しい順で返す。"""
    if not VIOLATION_LOG_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(VIOLATION_LOG_DIR.glob("*.json"), reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                for item in loaded:
                    if isinstance(item, dict):
                        item = {**item, "_log_date": path.stem}
                        out.append(item)
        except (json.JSONDecodeError, OSError):
            continue
    return out
