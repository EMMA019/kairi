"""検索スコープ・鮮度・市場ショートサーキットのテスト。"""
from app.core.chat_search import (
    balance_search_queries,
    named_reference_search_queries,
    should_skip_deep_fetch,
)
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
    # 引け後は業種クエリを夜間先物に差し替える場合あり
    assert any("業種" in q or "先物" in q for q in queries)
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
    assert any("業種" in q or "先物" in q for q in out["search_queries"])


def test_named_reference_forces_search_for_like_app():
    qs = named_reference_search_queries("ロジックラボみたいな教育アプリ作りたいな。アイディアください。")
    assert any("ロジックラボ" in q for q in qs)
    needed, queries = balance_search_queries(
        "ロジックラボみたいな教育アプリ作りたいな。アイディアください。",
        search_needed=False,
        search_queries=[],
    )
    assert needed is True
    assert any("ロジックラボ" in q for q in queries)
    assert named_reference_search_queries("こんなみたいな感じで") == []


def test_event_today_is_not_market_todayish():
    from app.core.chat_search import _is_todayish_market_query

    assert _is_todayish_market_query("今日埼玉か東京でイベント的なのあるかな？") is False
    assert _is_todayish_market_query("今日の日経どう？") is True


def test_drop_market_sources_on_event_query():
    from app.core.search_relevance import drop_offtopic_market_sources

    sources = [
        {"title": "埼玉のイベント【2026年8月16日】", "url": "https://walkerplus.com/event", "source": "walker"},
        {"title": "特別配当ネクソンがストップ高／日経平均続伸", "url": "https://news.yahoo.co.jp/zai", "source": "ZAi"},
        {"title": "来週の東京株式市場", "url": "https://www.reuters.com/jp", "source": "ロイター"},
    ]
    kept = drop_offtopic_market_sources("今日埼玉か東京でイベント的なのあるかな？", sources)
    titles = " ".join(s["title"] for s in kept)
    assert "イベント" in titles
    assert "ストップ高" not in titles
    assert "株式市場" not in titles

    market_kept = drop_offtopic_market_sources("今日の日経どう？", sources)
    assert len(market_kept) == 3


def test_drop_sec_8k_on_english_event_query():
    from app.core.search_relevance import drop_offtopic_market_sources

    sources = [
        {
            "title": "Tokyo kids events this weekend",
            "url": "https://www.japanforkids.com/events",
            "source": "japanforkids",
        },
        {
            "title": "8-K - NEIGHBORHOOD INTELLIGENCE, INC.",
            "url": "https://www.sec.gov/Archives/edgar/data/1130713/8-k.htm",
            "source": "SEC",
        },
        {
            "title": "INNSUITES HOSPITALITY TRUST (8-K)",
            "url": "https://www.sec.gov/cgi-bin/browse-edgar",
            "source": "EDGAR",
        },
    ]
    kept = drop_offtopic_market_sources(
        "Is there an event in Saitama or Tokyo today?",
        sources,
    )
    titles = " ".join(s["title"] for s in kept)
    assert "kids events" in titles
    assert "8-K" not in titles
    assert "EDGAR" not in " ".join(s.get("source") or "" for s in kept)

    finance_kept = drop_offtopic_market_sources("今日の日経どう？", sources)
    assert len(finance_kept) == 3


def test_drop_goldman_premarket_on_edu_app_query():
    from app.core.search_relevance import drop_offtopic_market_sources

    sources = [
        {
            "title": "ロジックラボ プログラミング思考アプリ",
            "url": "https://logiclab.example/app",
            "source": "logiclab",
        },
        {
            "title": "Goldman Sachs: biggest moves in premarket",
            "url": "https://www.bloomberg.com/premarket",
            "source": "Bloomberg",
        },
        {
            "title": "Sandisk is up more than 8% in premarket trading",
            "url": "https://finance.yahoo.com/news/sandisk",
            "source": "Yahoo",
        },
        {
            "title": "JPMorgan upgrades chip names",
            "url": "https://www.reuters.com/markets",
            "source": "Reuters",
        },
    ]
    kept = drop_offtopic_market_sources(
        "ロジックラボみたいな教育アプリ作りたいな",
        sources,
    )
    titles = " ".join(s["title"] for s in kept)
    assert "ロジックラボ" in titles
    assert "Goldman" not in titles
    assert "Sandisk" not in titles
    assert "JPMorgan" not in titles

    finance_kept = drop_offtopic_market_sources("今日の日経どう？", sources)
    assert len(finance_kept) == 4


def test_weekend_news_is_japan_not_events():
    from app.core.search_relevance import (
        drop_offtopic_event_sources,
        is_japanese_majority_query,
        is_news_briefing_query,
        news_briefing_search_queries,
    )

    q = "今週末のニュース教えて！"
    assert is_news_briefing_query(q) is True
    assert is_japanese_majority_query(q) is True
    needed, queries = balance_search_queries(q, search_needed=True, search_queries=["今週末 イベント"])
    blob = " ".join(queries)
    assert "日本" in blob or "Japan news" in blob
    assert "イベント" not in blob
    assert "今週末" not in blob

    sources = [
        {"title": "週末の姫路イベントまとめ", "url": "https://himeji.example/event", "source": "姫路の種"},
        {"title": "【水曜夜に読む週末占い】九星気学", "url": "https://uranai.example", "source": "占い"},
        {"title": "東日本で記録的豪雨 死者9人", "url": "https://www3.nhk.or.jp/news/rain", "source": "NHK"},
        {"title": "パリの週末：無料または低料金のお出かけアイデア", "url": "https://www.sortiraparis.com/weekend", "source": "Paris"},
    ]
    kept = drop_offtopic_event_sources(q, sources)
    titles = " ".join(s["title"] for s in kept)
    assert "豪雨" in titles
    assert "イベント" not in titles
    assert "占い" not in titles
    assert "パリ" not in titles

    outing_kept = drop_offtopic_event_sources("今日埼玉か東京でイベント的なのあるかな？", sources)
    assert len(outing_kept) == 4


def test_english_news_is_world_scope():
    from app.core.search_relevance import is_japanese_majority_query, news_briefing_search_queries

    q = "What's the news this weekend?"
    assert is_japanese_majority_query(q) is False
    needed, queries = balance_search_queries(q, search_needed=True, search_queries=["weekend events"])
    blob = " ".join(queries).lower()
    assert "world news" in blob or "international" in blob or "global news" in blob
    assert "weekend events" not in blob
    assert needed is True
    assert any("world" in q.lower() or "international" in q.lower() or "global" in q.lower() for q in news_briefing_search_queries(q))


def test_japan_morning_session_is_todayish():
    needed, queries = balance_search_queries(
        "7/29の日本市場前場がどんな感じだった？",
        search_needed=True,
        search_queries=["7月29日 日経平均 前場"],
    )
    assert needed is True
    blob = " ".join(queries)
    assert "日経" in blob
    assert "TOPIX" in blob
    assert "us japan stock dividend" not in blob.lower()


def test_market_today_shortcut_morning():
    out = _market_today_shortcut(
        "7/29の日本市場前場がどんな感じだった？",
        "2026-07-29",
        "July 29, 2026",
    )
    assert out is not None
    assert any("前場" in q for q in out["search_queries"])
    assert "tavily" in out["providers"]
    assert "brave" in out["providers"]
    assert "news" in out["providers"]


def test_explicit_us_date_not_overwritten_by_jst_today(monkeypatch):
    """JSTが7/30でも『7/29の米国市場』は7/29クエリになる。"""
    from datetime import datetime
    from app.core.chat_search import JST, balance_search_queries
    from app.core import chat_search as cs

    fake_now = datetime(2026, 7, 30, 6, 48, tzinfo=JST)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    monkeypatch.setattr(cs, "datetime", _FixedDatetime)

    needed, queries = balance_search_queries(
        "7/29の米国市場ってどうだった？",
        search_needed=True,
        search_queries=["junk"],
    )
    assert needed is True
    blob = " ".join(queries)
    assert "2026-07-29" in blob or "July 29" in blob
    assert "2026-07-30" not in blob
    assert "July 30" not in blob

    out = _market_today_shortcut(
        "7/29の米国市場ってどうだった？",
        "2026-07-30",
        "July 30, 2026",
    )
    assert out is not None
    qblob = " ".join(out["search_queries"])
    assert "2026-07-29" in qblob or "July 29" in qblob
    assert "2026-07-30" not in qblob
    assert "tavily" in out["providers"]


def test_us_anchor_without_date_uses_last_et_session():
    from datetime import datetime
    from app.core.chat_search import JST, resolve_market_anchor_date

    # JST 7/30 06:48 = ET 7/29 17:48 after hours → last session 7/29
    now = datetime(2026, 7, 30, 6, 48, tzinfo=JST)
    d = resolve_market_anchor_date("米国市場どうだった？", market="us", now_jst=now)
    assert d.isoformat() == "2026-07-29"


def test_jp_today_queries_use_live_price_word_during_morning(monkeypatch):
    """場中は検索クエリに『終値』を硬直指定しない。"""
    from datetime import datetime
    from app.core.chat_search import JST, balance_search_queries
    from app.core import chat_search as cs

    fake_now = datetime(2026, 7, 30, 11, 0, tzinfo=JST)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    monkeypatch.setattr(cs, "datetime", _FixedDatetime)
    needed, queries = balance_search_queries(
        "日本市場今日はどう？",
        search_needed=True,
        search_queries=["junk"],
    )
    assert needed is True
    blob = " ".join(queries)
    assert "現在値" in blob
    assert "日経平均 終値" not in blob


def test_jp_evening_queries_include_night_futures(monkeypatch):
    from datetime import datetime
    from app.core.chat_search import JST, balance_search_queries
    from app.core import chat_search as cs

    fake_now = datetime(2026, 7, 30, 18, 42, tzinfo=JST)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    monkeypatch.setattr(cs, "datetime", _FixedDatetime)
    _, queries = balance_search_queries(
        "日本市場今日はどうだった?",
        search_needed=True,
        search_queries=["junk"],
    )
    blob = " ".join(queries)
    assert "終値" in blob
    assert "日経225先物 夜間取引" in blob


def test_skip_deep_fetch_for_close():
    assert should_skip_deep_fetch("今日の日本市場はどうだった？") is True
    assert should_skip_deep_fetch("Pythonの書き方教えて") is False


def test_no_skip_deep_fetch_when_date_is_explicit():
    # 明示日付つき市況はスニペットが薄く、確定終値を取りに行く必要がある
    assert should_skip_deep_fetch("7/29の日本市場前場") is False
    assert should_skip_deep_fetch("8/6の米国市場の終値") is False


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


def test_rerank_demotes_stale_ath_headline():
    query = "7/29 日本市場 前場 日経平均"
    results = [
        {
            "title": "日経平均株価、最高値更新　終値1636円高の6万6329円に反発 - 日本経済新聞",
            "snippet": "2026年5月22日の東京株式市場。日経平均は大幅続伸。",
            "url": "https://www.nikkei.com/old-ath",
        },
        {
            "title": "日経平均前場 続落 半導体売り - 東京株式市場",
            "snippet": "2026年7月29日 前場の東京株式。日経平均は売り優勢。",
            "url": "https://www.nikkei.com/today-morning",
        },
        {
            "title": "Stocks making the biggest moves premarket: Micron, Exxon",
            "snippet": "Premarket movers after hours.",
            "url": "https://www.cnbc.com/premarket-junk",
        },
    ]
    ranked = rerank(query, results, top_k=3)
    assert ranked[0]["url"] == "https://www.nikkei.com/today-morning"

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
