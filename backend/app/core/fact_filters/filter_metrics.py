"""fact_filters 各段の発火回数。テキストが変わった回数だけ数える。"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.utils.logger import get_logger

logger = get_logger(__name__)

_LOCK = threading.Lock()
_COUNTS: dict[str, int] = {}
_CHANGED: dict[str, int] = {}  # 実際に本文が変わった回数
_CALLS: dict[str, int] = {}

_METRICS_PATH = Path(__file__).resolve().parents[3] / "storage" / "filter_metrics.json"


def reset_filter_metrics() -> None:
    with _LOCK:
        _COUNTS.clear()
        _CHANGED.clear()
        _CALLS.clear()


def bump_filter(name: str, *, changed: bool) -> None:
    with _LOCK:
        _CALLS[name] = _CALLS.get(name, 0) + 1
        if changed:
            _CHANGED[name] = _CHANGED.get(name, 0) + 1
            _COUNTS[name] = _COUNTS.get(name, 0) + 1


def track_filter(name: str, before: str, after: str) -> str:
    bump_filter(name, changed=(before or "") != (after or ""))
    return after


def wrap_text_filter(name: str, fn: Callable[..., str], *args, **kwargs) -> str:
    """str→str フィルタ用。"""
    # 第1引数が text 前提
    before = args[0] if args else kwargs.get("text", "")
    if not isinstance(before, str):
        before = str(before or "")
    after = fn(*args, **kwargs)
    if not isinstance(after, str):
        after = str(after or "")
    return track_filter(name, before, after)


def wrap_tuple_filter(name: str, fn: Callable[..., tuple], *args, **kwargs) -> tuple:
    """(bool, str) などタプル先頭以外に text がある場合は fn 側で扱う。
    ここでは戻り値の最後が str と仮定して差分を取る。
    """
    before = args[0] if args else ""
    if not isinstance(before, str):
        before = str(before or "")
    result = fn(*args, **kwargs)
    after = before
    if isinstance(result, tuple) and result:
        for part in reversed(result):
            if isinstance(part, str):
                after = part
                break
    track_filter(name, before, after)
    return result


def get_filter_metrics_snapshot() -> dict[str, Any]:
    with _LOCK:
        changed = dict(sorted(_CHANGED.items(), key=lambda kv: (-kv[1], kv[0])))
        calls = dict(_CALLS)
    dead = [name for name, n in calls.items() if changed.get(name, 0) == 0]
    return {
        "changed": changed,
        "calls": calls,
        "dead_filters": dead,
        "total_changes": sum(changed.values()),
    }


def persist_filter_metrics() -> None:
    """プロセス累計を日次ファイルへマージ保存。"""
    snap = get_filter_metrics_snapshot()
    _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if _METRICS_PATH.exists():
        try:
            with open(_METRICS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    day = datetime.now().strftime("%Y-%m-%d")
    by_day = existing.setdefault("by_day", {})
    day_entry = by_day.setdefault(day, {"changed": {}, "calls": {}})
    for name, n in snap["changed"].items():
        # スナップショットはプロセス累計なので、日次は「最終既知」で上書きする
        day_entry["changed"][name] = n
    for name, n in snap["calls"].items():
        day_entry["calls"][name] = n
    existing["updated_at"] = datetime.now().isoformat()
    existing["process"] = snap

    try:
        with open(_METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning(f"filter metrics persist failed: {e}")


def load_persisted_filter_metrics() -> dict[str, Any]:
    if not _METRICS_PATH.exists():
        return {}
    try:
        with open(_METRICS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
