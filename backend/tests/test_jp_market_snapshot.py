"""JP market snapshot の構造テスト（ネットワーク不要）。"""
from unittest.mock import patch

from app.core.tools.market_data import (
    _normalize_ticker,
    format_jp_market_snapshot_for_prompt,
    get_jp_market_snapshot,
)


def test_normalize_topix_and_nikkei():
    assert _normalize_ticker("TOPIX") == "^TOPX"
    assert _normalize_ticker("Nikkei 225") == "^N225"
    assert _normalize_ticker("^N225") == "^N225"


def test_jp_snapshot_structure_with_mock():
    fake = {
        "ticker": "^N225",
        "name": "Nikkei 225",
        "current_price": 64931.19,
        "previous_close": 64611.15,
        "change": 320.04,
        "change_pct": 0.50,
        "open": 65164.98,
        "day_low": 64123.4,
        "day_high": 65220.69,
        "52_week_low": None,
        "52_week_high": None,
        "volume": None,
        "dividend_yield": None,
        "trailing_pe": None,
        "forward_pe": None,
        "market_cap": None,
        "currency": "JPY",
    }

    def fake_quote(ticker: str):
        q = dict(fake)
        q["ticker"] = ticker
        if ticker == "^TOPX":
            q["current_price"] = 2800.0
            q["previous_close"] = 2790.0
            q["change"] = 10.0
            q["change_pct"] = 0.36
        return q

    with patch("app.core.tools.market_data._quote_dict", side_effect=fake_quote):
        snap = get_jp_market_snapshot(include_sectors=True)
        assert "^N225" in snap["indices"]
        assert "^TOPX" in snap["indices"]
        assert "1631.T" in snap["sectors"]
        text = format_jp_market_snapshot_for_prompt("今日の日本市場")
        assert "日経平均" in text or "^N225" in text
        assert "TOPIX" in text
        assert "推測禁止" in text
        assert "未確認" in text
