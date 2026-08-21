"""SQLite queue for promo drafts (WAL)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parents[3] / "storage" / "promo.db"

STATUSES = ("draft", "approved", "posted", "rejected")
CHANNELS = ("discord", "github")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_promo_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                channel TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                posted_at TEXT,
                error TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_status ON drafts(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_fp ON drafts(fingerprint)")
        conn.commit()


def insert_draft(
    *,
    channel: str,
    title: str,
    body: str,
    fingerprint: str,
    metrics_json: str,
) -> dict[str, Any]:
    init_promo_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO drafts (created_at, status, channel, title, body, fingerprint, metrics_json)
            VALUES (?, 'draft', ?, ?, ?, ?, ?)
            """,
            (now, channel, title, body, fingerprint, metrics_json),
        )
        conn.commit()
        row_id = cur.lastrowid
    return get_draft(int(row_id))  # type: ignore[arg-type]


def get_draft(draft_id: int) -> dict[str, Any]:
    init_promo_db()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not row:
        raise KeyError(draft_id)
    return dict(row)


def list_drafts(status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    init_promo_db()
    limit = max(1, min(int(limit), 200))
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drafts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def update_draft(
    draft_id: int,
    *,
    body: Optional[str] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    posted_at: Optional[str] = None,
) -> dict[str, Any]:
    init_promo_db()
    row = get_draft(draft_id)
    if body is not None:
        row["body"] = body
    if title is not None:
        row["title"] = title
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"invalid status: {status}")
        row["status"] = status
    if error is not None:
        row["error"] = error
    if posted_at is not None:
        row["posted_at"] = posted_at
    with _connect() as conn:
        conn.execute(
            """
            UPDATE drafts
            SET title = ?, body = ?, status = ?, error = ?, posted_at = ?
            WHERE id = ?
            """,
            (row["title"], row["body"], row["status"], row.get("error"), row.get("posted_at"), draft_id),
        )
        conn.commit()
    return get_draft(draft_id)


def find_recent_fingerprint(fingerprint: str, days: int = 7) -> Optional[dict[str, Any]]:
    init_promo_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM drafts
            WHERE fingerprint = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (fingerprint,),
        ).fetchall()
    if not rows:
        return None
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    for row in rows:
        created = str(row["created_at"] or "")
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = 0
        if ts >= cutoff:
            return dict(row)
    return None


def posted_today_count() -> int:
    init_promo_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM drafts
            WHERE status = 'posted' AND (
                posted_at LIKE ? OR (posted_at IS NULL AND created_at LIKE ?)
            )
            """,
            (f"{today}%", f"{today}%"),
        ).fetchone()
    return int(row["n"] if row else 0)
