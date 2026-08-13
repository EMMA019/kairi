"""Content-Age Contract: transport time vs observation time."""

from app.core.content_age import (
    format_quote_clocks,
    format_source_clocks,
    result_content_time,
    result_fetch_time,
    stamp_quote_freshness,
)
from app.core.search.formatter import _result_published, format_for_prompt, format_results


def test_stamp_quote_sets_dual_clocks():
    q = stamp_quote_freshness(
        {"ticker": "SPY", "current_price": 1.0, "price_kind": "session_close_or_last"},
        content_as_of="2026-08-11",
        fetched_at="2026-08-12T01:00:00Z",
    )
    assert q["content_as_of"] == "2026-08-11"
    assert q["fetched_at"] == "2026-08-12T01:00:00Z"
    assert not q.get("content_stale")


def test_previous_close_fallback_marks_stale_content():
    q = stamp_quote_freshness(
        {
            "ticker": "SPY",
            "current_price": 500.0,
            "price_kind": "previous_close_fallback",
        },
        content_as_of="2026-08-11",
    )
    assert q["content_stale"] is True
    assert "previous_close" in q["content_stale_reason"]


def test_result_content_time_never_falls_back_to_fetched_at():
    item = {"fetched_at": "2026-08-12T10:00:00Z", "title": "x"}
    assert result_content_time(item) == ""
    assert result_fetch_time(item) == "2026-08-12T10:00:00Z"
    assert _result_published(item) == ""


def test_result_content_time_prefers_published():
    item = {
        "published": "2026-08-10T12:00:00Z",
        "fetched_at": "2026-08-12T10:00:00Z",
    }
    assert result_content_time(item) == "2026-08-10T12:00:00Z"
    clocks = format_source_clocks(item)
    assert "published: 2026-08-10T12:00:00Z" in clocks
    assert "fetched_at: 2026-08-12T10:00:00Z" in clocks


def test_format_results_keeps_clocks_separate():
    results = format_results(
        [
            {
                "title": "A",
                "snippet": "s",
                "url": "https://example.com/a",
                "source": "wire",
                "published": "2026-08-10",
                "fetched_at": "2026-08-12T01:00:00Z",
            }
        ],
        query="markets",
    )
    assert results
    assert results[0]["published"] == "2026-08-10"
    assert results[0]["fetched_at"] == "2026-08-12T01:00:00Z"


def test_format_for_prompt_does_not_label_fetch_as_published():
    text = format_for_prompt(
        [
            {
                "title": "Only fetched",
                "snippet": "body",
                "url": "https://example.com/b",
                "source": "pool",
                "fetched_at": "2026-08-12T09:00:00Z",
            }
        ],
        query="test",
    )
    assert "published: unknown" in text
    assert "fetched_at: 2026-08-12T09:00:00Z" in text
    # Must not present fetch time alone as published:
    assert "(published: 2026-08-12T09:00:00Z)" not in text


def test_format_quote_clocks_includes_stale_flag():
    label = format_quote_clocks(
        {
            "content_as_of": "2026-08-11",
            "fetched_at": "2026-08-12T01:00:00Z",
            "content_stale": True,
            "content_stale_reason": "session_bar_missing",
        },
        session_date="2026-08-12",
    )
    assert "content_as_of=2026-08-11" in label
    assert "fetched_at=2026-08-12T01:00:00Z" in label
    assert "session_date=2026-08-12" in label
    assert "STALE_CONTENT" in label
