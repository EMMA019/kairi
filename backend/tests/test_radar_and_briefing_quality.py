"""レーダー誤マッチ・ATH・カレンダー休場ラベル・ブリーフHN除外の回帰テスト。"""
from datetime import datetime, timezone, timedelta

from app.core.monitor.watchlist import (
    extract_matched_targets_and_entities,
    systematic_screen_and_score,
)
from app.core.market_calendar import format_market_status
from app.core.briefing.generator import (
    _is_briefing_noise_source,
    _is_stale_jp_close_headline,
)

JST = timezone(timedelta(hours=9))


def test_education_does_not_match_cat_or_dividend_etfs():
    targets, entities = extract_matched_targets_and_entities(
        "grand canyon education outlines path to hybrid locations".lower()
    )
    assert "CAT" not in entities
    assert "^HDV" not in targets
    assert "^DGRO" not in targets
    assert "^DIV_TOP_ETFS" not in targets


def test_quarter_does_not_match_ter_soxx():
    targets, entities = extract_matched_targets_and_entities(
        "lvmh fashion and leather division reports 1% organic growth in second quarter".lower()
    )
    assert "TER" not in entities
    assert "^SOXX" not in targets


def test_earnings_does_not_match_gs_via_substring():
    targets, entities = extract_matched_targets_and_entities(
        "company reported strong quarterly earnings beat".lower()
    )
    assert "GS" not in entities


def test_path_does_not_trigger_ath_catalyst():
    item = {
        "title": "Grand Canyon Education outlines path to 80 hybrid locations",
        "summary": "Company plans to open a law school.",
        "source": "Seeking Alpha",
        "url": "https://example.com/path-to-growth",
    }
    scored = systematic_screen_and_score(item)
    cats = " ".join(scored.get("detected_catalysts") or [])
    assert "最高値" not in cats
    assert "時価総額最高" not in cats


def test_real_ath_still_detected():
    item = {
        "title": "Nvidia hits all-time high as AI demand soars",
        "summary": "Shares set a record high.",
        "source": "Reuters",
        "url": "https://example.com/nvda-ath",
    }
    scored = systematic_screen_and_score(item)
    cats = " ".join(scored.get("detected_catalysts") or [])
    assert "最高値" in cats or "時価総額" in cats


def test_jp_outside_hours_not_labeled_kyujitsu():
    # 金曜 08:15 JST = 取引時間外だが通常営業日
    dt = datetime(2026, 7, 31, 8, 15, tzinfo=JST)
    text = format_market_status(dt)
    assert "取引時間外（本日は通常営業日）" in text
    assert "休場 (outside_trading_hours)" not in text


def test_briefing_excludes_hacker_news():
    assert _is_briefing_noise_source({"source": "Hacker News", "url": "https://news.ycombinator.com/item?id=1"})
    assert not _is_briefing_noise_source({"source": "Reuters", "url": "https://www.reuters.com/x"})


def test_preopen_drops_stale_nikkei_close_headline():
    today = datetime(2026, 7, 31, 8, 15, tzinfo=JST)
    stale = {
        "title": "日経平均終値930円安、SK好決算「力不足」",
        "published": "2026-07-30T06:00:00Z",
        "summary": "",
    }
    assert _is_stale_jp_close_headline(stale, "preopen", today) is True
    assert _is_stale_jp_close_headline(stale, "postclose", today) is False
