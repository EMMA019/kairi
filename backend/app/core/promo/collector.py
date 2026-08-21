"""Collect promo facts from local telemetry only (no invented stats)."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.app_version import APP_VERSION
from app.utils.logger import get_logger

logger = get_logger(__name__)


def collect_telemetry() -> dict[str, Any]:
    """Return a JSON-serializable snapshot. Missing sources are omitted, not guessed."""
    out: dict[str, Any] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "app_name": "Kairi",
    }
    _attach_filter_metrics(out)
    _attach_integrity(out)
    _attach_violations(out)
    _attach_latency(out)
    _attach_eval_case_count(out)
    return out


def _attach_filter_metrics(out: dict[str, Any]) -> None:
    try:
        from app.core.fact_filters.filter_metrics import (
            get_filter_metrics_snapshot,
            load_persisted_filter_metrics,
        )

        snap = get_filter_metrics_snapshot()
        hits = snap.get("changed") or {}
        if not hits:
            persisted = load_persisted_filter_metrics() or {}
            by_day = persisted.get("by_day") or {}
            if by_day:
                latest = by_day[sorted(by_day.keys())[-1]]
                hits = latest.get("changed") or {}
        if hits:
            top = sorted(hits.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:8]
            out["filter_hits"] = {k: int(v) for k, v in top}
            out["filter_total_changes"] = sum(int(v) for v in hits.values())
    except Exception as e:
        logger.debug(f"promo filter metrics skipped: {e}")


def _attach_integrity(out: dict[str, Any]) -> None:
    try:
        import sqlite3
        from app.core.database import DB_PATH

        if not Path(DB_PATH).exists():
            return
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(verified_facts), 0),
                    COALESCE(SUM(unverified_facts), 0),
                    COALESCE(SUM(citations), 0),
                    COUNT(*)
                FROM integrity_stats
                """
            ).fetchone()
        if row:
            out["verified_facts"] = int(row[0] or 0)
            out["unverified_facts"] = int(row[1] or 0)
            out["citations"] = int(row[2] or 0)
            out["search_executions"] = int(row[3] or 0)
    except Exception as e:
        logger.debug(f"promo integrity skipped: {e}")


def _attach_violations(out: dict[str, Any]) -> None:
    try:
        from app.core.violation_log import iter_all_violation_logs

        logs = iter_all_violation_logs() or []
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent = []
        for item in logs:
            ts = str(item.get("timestamp") or item.get("created_at") or "")
            keep = True
            if ts:
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    keep = parsed >= cutoff
                except ValueError:
                    keep = True
            if keep:
                recent.append(item)
        if recent:
            types = Counter(str(i.get("violation_type") or "その他") for i in recent)
            out["violation_count_7d"] = len(recent)
            out["violation_types_7d"] = dict(types.most_common(8))
    except Exception as e:
        logger.debug(f"promo violations skipped: {e}")


def _attach_latency(out: dict[str, Any]) -> None:
    try:
        from app.core.latency_metrics import get_latency_snapshot

        snap = get_latency_snapshot() or {}
        n = int(snap.get("sample_count") or 0)
        if n <= 0:
            return
        out["latency_sample_count"] = n
        for key in (
            "ttft_p50_ms",
            "ttft_p95_ms",
            "supervisor_skip_rate",
            "avg_supervisor_loops",
            "search_p50_ms",
        ):
            if snap.get(key) is not None:
                out[key] = snap[key]
    except Exception as e:
        logger.debug(f"promo latency skipped: {e}")


def _attach_eval_case_count(out: dict[str, Any]) -> None:
    try:
        cases = Path(__file__).resolve().parents[3] / "evals" / "cases"
        if cases.is_dir():
            n = len(list(cases.glob("*.yaml")))
            if n:
                out["eval_case_count"] = n
    except Exception as e:
        logger.debug(f"promo eval count skipped: {e}")


def fingerprint_for(metrics: dict[str, Any]) -> str:
    """Coarse hash so identical daily telemetry is not re-queued."""
    import hashlib

    bucket_ttft = metrics.get("ttft_p50_ms")
    if isinstance(bucket_ttft, (int, float)):
        bucket_ttft = int(bucket_ttft) // 50
    payload = {
        "v": metrics.get("app_version"),
        "filters": metrics.get("filter_total_changes"),
        "violations": metrics.get("violation_count_7d"),
        "ttft_bucket": bucket_ttft,
        "evals": metrics.get("eval_case_count"),
        "day": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
