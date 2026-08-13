"""フィルタ発火メトリクス。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.fact_filters.filter_metrics import (
    get_filter_metrics_snapshot,
    reset_filter_metrics,
    track_filter,
)
from app.core.fact_filters.pipeline import apply_grounding_pipeline


def test_track_filter_counts_changes_only():
    reset_filter_metrics()
    track_filter("noop", "same", "same")
    track_filter("changer", "a", "b")
    snap = get_filter_metrics_snapshot()
    assert snap["calls"]["noop"] == 1
    assert snap["changed"].get("noop", 0) == 0
    assert snap["changed"]["changer"] == 1
    assert "noop" in snap["dead_filters"]


def test_pipeline_records_caution_signal_without_body_append():
    reset_filter_metrics()
    src = "[1] Dow rose about 0.5% on July 24, 2026. Exact closing points not listed."
    text = "ダウ工業株30種平均は44,342.19ポイントで引けました。"
    out = apply_grounding_pipeline(text, src, "7/24のダウ終値は？")
    # 注意喚起は UI 常設のため本文は変えない
    assert "AIは間違えることがあります" not in out
    assert "AI can make mistakes" not in out
    snap = get_filter_metrics_snapshot()
    assert snap["changed"].get("ai_caution_signal", 0) >= 1
