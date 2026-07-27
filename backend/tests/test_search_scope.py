"""検索スコープ・鮮度・市場ショートサーキットのテスト。"""
from app.core.chat_search import balance_search_queries, should_skip_deep_fetch
from app.core.search_planner import _market_today_shortcut
from app.core.search.reranker import rerank, _freshness_score, _jp_market_noise_penalty


def test_japan_market_does_not_add_us_etf():
    needed, queries = balance_search_queries(
        "今日の日本市場はどうだった？",
        search_needed=True,
        search_queries=["東京株式市場 今日"],
    )
    assert needed is True
    blob = " ".join(queries).lower()
    assert "us japan stock dividend" not in blob
    assert any("日経" in q or "東京" in q for q in queries)
    assert any("TOPIX" in q for q in queries)
    assert any("業種" in q for q in queries)
    assert len(queries) >= 3


def test_japan_finance_followup_queries():
    needed, queries = balance_search_queries(
        "金融セクターとか好調じゃない？ TOPIXは？",
        search_needed=True,
        search_queries=["セクターローテーション"],
    )
    assert needed is True
    blob = " ".join(queries)
    assert "TOPIX" in blob or "業種" in blob or "銀行" in blob


def test_us_market_does_not_add_japan_etf_mix():
    needed, queries = balance_search_queries(
        "米国市場は7/27はどう動くと思う？",
        search_needed=True,
        search_queries=["US stock market"],
    )
    assert needed is True
    blob = " ".join(queries)
    assert "US Japan stock dividend ETF market outlook 2026" not in blob


def test_market_today_shortcut_japan():
    out = _market_today_shortcut("今日の日本市場はどうだった？", "2026-07-27", "July 27, 2026")
    assert out is not None
    assert out["needs_search"] is True
    assert out["category"] == "finance"
    assert any("日経" in q for q in out["search_queries"])
    assert any("TOPIX" in q for q in out["search_queries"])
    assert any("業種" in q for q in out["search_queries"])


def test_skip_deep_fetch_for_close():
    assert should_skip_deep_fetch("今日の日本市場はどうだった？") is True
    assert should_skip_deep_fetch("Pythonの書き方教えて") is False


def test_rerank_prefers_fresh_date():
    query = "今日の日本市場 終値"
    results = [
        {
            "title": "Stocks Sink in Broad AI Rout Sparked by China's DeepSeek - WSJ",
            "snippet": "January 27, 2025 AI stocks plunged after DeepSeek news.",
            "url": "https://www.wsj.com/old-deepseek",
        },
        {
            "title": "日経平均大引け 反発 320円高の6万4931円 - 日本経済新聞",
            "snippet": "2026年7月27日の東京株式市場。日経平均は終値6万4931円。",
            "url": "https://www.nikkei.com/today-close",
        },
    ]
    ranked = rerank(query, results, top_k=2)
    assert ranked[0]["url"] == "https://www.nikkei.com/today-close"
    fresh = _freshness_score(query, results[1]["title"], results[1]["snippet"])
    stale = _freshness_score(query, results[0]["title"], results[0]["snippet"])
    assert fresh > stale


def test_rerank_demotes_mortgage_for_jp_market():
    query = "今日の日本市場 日経平均 終値"
    results = [
        {
            "title": "Mortgage and refinance interest rates today, Sunday, July 26, 2026: Rates up",
            "snippet": "Best mortgage rates. CD rates provide 4.20% APY.",
            "url": "https://example.com/mortgage",
        },
        {
            "title": "日経平均大引け 反発 — 東京株式市場",
            "snippet": "2026年7月27日 日経平均終値とTOPIX。東証業種別も発表。",
            "url": "https://www.nikkei.com/market",
        },
        {
            "title": "Best CD rates today: Lock in up to 4.20% APY",
            "snippet": "Highest savings APY this year.",
            "url": "https://example.com/cd-rates",
        },
    ]
    ranked = rerank(query, results, top_k=3)
    assert ranked[0]["url"] == "https://www.nikkei.com/market"
    assert _jp_market_noise_penalty(query, results[0]["title"], results[0]["snippet"]) < -20
