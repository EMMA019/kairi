"""Grounding consolidation: supervisor hygiene stays light; full pipeline is finalize-only."""
from app.core.fact_filters import CONSOLIDATION_NOTES, filter_fact
from app.core.fact_filters.pipeline import apply_grounding_pipeline


def test_consolidation_notes_document_split():
    assert "supervisor_filter_fact" in CONSOLIDATION_NOTES


def test_filter_fact_keeps_advice_hygiene():
    raw = "確度 85% で買うべき局面です"
    out = filter_fact(raw)
    assert "売買判断" in out or "資金配分" in out


def test_filter_fact_skips_heavy_pipeline_overlap():
    """曜日など重いチェックは finalize 側へ移したので、filter_fact 単独では消えない。"""
    # strip_unverified_day_of_week は source 無しだと除去しうるが、
    # filter_fact からは外したのでプレースホルダ曜日が残る想定。
    raw = "来たる水曜日に決算発表があります。"
    assert filter_fact(raw) == raw or "水曜日" in filter_fact(raw)


def test_full_pipeline_smoke():
    assert callable(apply_grounding_pipeline)
    out = apply_grounding_pipeline("Hello world.", "", user_input="hi")
    assert "Hello world." in out
