"""
Graded news-feed health (inspired by Content-Age / seed-health ideas).

Per-feed statuses are not binary. Fleet verdict aggregates them without
flapping the HTTP status on partial degradation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

# Per-feed
OK = "OK"
EMPTY = "EMPTY"
STALE_SEED = "STALE_SEED"
COVERAGE_PARTIAL = "COVERAGE_PARTIAL"
SEED_ERROR = "SEED_ERROR"
UNKNOWN = "UNKNOWN"

# Fleet
HEALTHY = "HEALTHY"
WARNING = "WARNING"
DEGRADED = "DEGRADED"
UNHEALTHY = "UNHEALTHY"

_STALE_AFTER = timedelta(hours=24)
_FAIL_SOFT = 1
_FAIL_HARD = 3


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s.replace("Z", ""), fmt.replace("Z", ""))
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def grade_feed(feed: dict[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Attach status + reasons to a feed_health row."""
    now = now or datetime.utcnow()
    out = dict(feed)
    fails = int(feed.get("consecutive_failures") or 0)
    last_count = int(feed.get("last_item_count") or 0)
    last_success = _parse_ts(feed.get("last_success"))
    reasons: list[str] = []

    if fails >= _FAIL_HARD:
        status = SEED_ERROR
        reasons.append(f"consecutive_failures={fails}")
    elif fails >= _FAIL_SOFT:
        status = COVERAGE_PARTIAL
        reasons.append(f"consecutive_failures={fails}")
    elif last_success is None:
        status = UNKNOWN
        reasons.append("never_succeeded")
    elif now - last_success > _STALE_AFTER:
        status = STALE_SEED
        reasons.append(f"last_success_age_h={(now - last_success).total_seconds() / 3600:.1f}")
    elif last_count <= 0:
        status = EMPTY
        reasons.append("last_item_count=0")
    else:
        status = OK

    out["status"] = status
    out["status_reasons"] = reasons
    return out


def grade_fleet(
    feeds: list[dict[str, Any]],
    *,
    pool_total: int,
    pool_last_18h: int,
) -> dict[str, Any]:
    """
    Aggregate per-feed grades into a fleet verdict.

    `ok` remains loosely True unless the fleet is UNHEALTHY — monitors that
    only check a boolean keep working; clients that care use `verdict`.
    """
    graded = [grade_feed(f) for f in feeds]
    counts = {
        OK: 0,
        EMPTY: 0,
        STALE_SEED: 0,
        COVERAGE_PARTIAL: 0,
        SEED_ERROR: 0,
        UNKNOWN: 0,
    }
    for g in graded:
        counts[g["status"]] = counts.get(g["status"], 0) + 1

    n = len(graded) or 1
    err = counts[SEED_ERROR]
    soft = counts[COVERAGE_PARTIAL] + counts[STALE_SEED] + counts[EMPTY]
    pool_thin = pool_last_18h == 0 and pool_total == 0

    if graded and err == len(graded) and pool_thin:
        verdict = UNHEALTHY
    elif err >= max(2, n // 3) or (err >= 1 and pool_thin):
        verdict = DEGRADED
    elif err >= 1 or soft >= 1 or (pool_last_18h == 0 and pool_total > 0):
        verdict = WARNING
    else:
        verdict = HEALTHY

    problems = [g for g in graded if g["status"] != OK]
    return {
        "verdict": verdict,
        "ok": verdict != UNHEALTHY,
        "status_counts": counts,
        "feeds": graded,
        "feeds_failing": err,
        "feeds_problem": len(problems),
        "pool_total": pool_total,
        "pool_last_18h": pool_last_18h,
    }
