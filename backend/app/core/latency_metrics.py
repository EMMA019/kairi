"""Chat latency / loop metrics (TTFT, supervisor skip, search).

Persisted under storage/latency_metrics.json so Integrity can show a speed panel.
Does not claim win-rate vs commercial products — numbers only.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

_LOCK = threading.Lock()
_SAMPLES: list[dict[str, Any]] = []
_MAX_SAMPLES = 400
_METRICS_PATH = Path(__file__).resolve().parents[2] / "storage" / "latency_metrics.json"


def reset_latency_metrics() -> None:
    with _LOCK:
        _SAMPLES.clear()


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 1)
    idx = min(len(sorted_vals) - 1, max(0, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
    return round(sorted_vals[idx], 1)


def record_latency(
    *,
    first_sse_ms: float | None,
    first_chunk_ms: float | None,
    search_ms: float = 0.0,
    supervisor_ms: float = 0.0,
    total_ms: float | None = None,
    supervisor_skipped: bool = False,
    supervisor_loops: int = 0,
) -> dict[str, Any]:
    sample = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "first_sse_ms": round(first_sse_ms, 1) if first_sse_ms is not None else None,
        "first_chunk_ms": round(first_chunk_ms, 1) if first_chunk_ms is not None else None,
        "search_ms": round(search_ms or 0.0, 1),
        "supervisor_ms": round(supervisor_ms or 0.0, 1),
        "total_ms": round(total_ms, 1) if total_ms is not None else None,
        "supervisor_skipped": bool(supervisor_skipped),
        "supervisor_loops": int(supervisor_loops or 0),
    }
    with _LOCK:
        _SAMPLES.append(sample)
        if len(_SAMPLES) > _MAX_SAMPLES:
            del _SAMPLES[: len(_SAMPLES) - _MAX_SAMPLES]
        snapshot = _snapshot_unlocked()
    _persist(snapshot)
    return sample


def _snapshot_unlocked() -> dict[str, Any]:
    n = len(_SAMPLES)
    ttft = [s["first_chunk_ms"] for s in _SAMPLES if isinstance(s.get("first_chunk_ms"), (int, float))]
    sse = [s["first_sse_ms"] for s in _SAMPLES if isinstance(s.get("first_sse_ms"), (int, float))]
    search = [s["search_ms"] for s in _SAMPLES if isinstance(s.get("search_ms"), (int, float))]
    sup = [s["supervisor_ms"] for s in _SAMPLES if isinstance(s.get("supervisor_ms"), (int, float))]
    total = [s["total_ms"] for s in _SAMPLES if isinstance(s.get("total_ms"), (int, float))]
    skipped = sum(1 for s in _SAMPLES if s.get("supervisor_skipped"))
    loops = [int(s.get("supervisor_loops") or 0) for s in _SAMPLES]
    ttft.sort()
    sse.sort()
    search.sort()
    sup.sort()
    total.sort()
    return {
        "sample_count": n,
        "ttft_p50_ms": _percentile(ttft, 50),
        "ttft_p95_ms": _percentile(ttft, 95),
        "first_sse_p50_ms": _percentile(sse, 50),
        "search_p50_ms": _percentile(search, 50),
        "supervisor_p50_ms": _percentile(sup, 50),
        "total_p50_ms": _percentile(total, 50),
        "supervisor_skip_rate": round(skipped / n, 3) if n else 0.0,
        "supervisor_skip_count": skipped,
        "avg_supervisor_loops": round(sum(loops) / n, 2) if n else 0.0,
    }


def get_latency_snapshot() -> dict[str, Any]:
    with _LOCK:
        snap = _snapshot_unlocked()
        recent = list(_SAMPLES[-20:])
    if snap["sample_count"] == 0:
        persisted = load_persisted_latency_metrics()
        if persisted:
            return persisted
    snap["recent"] = recent
    return snap


def load_persisted_latency_metrics() -> dict[str, Any]:
    if not _METRICS_PATH.exists():
        return {}
    try:
        with open(_METRICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _persist(snapshot: dict[str, Any]) -> None:
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(snapshot)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = _METRICS_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(_METRICS_PATH)
    except OSError as e:
        logger.debug(f"latency metrics persist skipped: {e}")


class LatencyProbe:
    """Wraps an SSE generator and records first-event / first-chunk times."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.first_sse_ms: float | None = None
        self.first_chunk_ms: float | None = None

    def observe_sse(self, chunk: str) -> None:
        now_ms = (time.perf_counter() - self.t0) * 1000.0
        if self.first_sse_ms is None:
            self.first_sse_ms = now_ms
        if self.first_chunk_ms is not None:
            return
        for block in (chunk or "").split("\n\n"):
            for line in block.splitlines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("type") == "chunk":
                    self.first_chunk_ms = now_ms
                    return

    def finish(
        self,
        *,
        search_ms: float = 0.0,
        supervisor_ms: float = 0.0,
        supervisor_skipped: bool = False,
        supervisor_loops: int = 0,
    ) -> dict[str, Any]:
        total_ms = (time.perf_counter() - self.t0) * 1000.0
        try:
            return record_latency(
                first_sse_ms=self.first_sse_ms,
                first_chunk_ms=self.first_chunk_ms,
                search_ms=search_ms,
                supervisor_ms=supervisor_ms,
                total_ms=total_ms,
                supervisor_skipped=supervisor_skipped,
                supervisor_loops=supervisor_loops,
            )
        except Exception as e:
            logger.debug(f"latency record skipped: {e}")
            return {}
