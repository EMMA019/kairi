"""検索スコープ・鮮度・市場ショートサーキットのテスト。"""
from app.core.chat_search import balance_search_queries, should_skip_deep_fetch
from app.core.search_planner import _market_today_shortcut
from app.core.search.reranker import rerank, _freshness_score


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
