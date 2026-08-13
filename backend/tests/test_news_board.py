"""News Desk board: region tagging + /api/news/board data path."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_board_keeps_per_region_slots(tmp_path, monkeypatch):
    """Yonhap が日付で上位を占めても US/JP レーンが空にならない。"""
    async def _run():
        import app.core.news.database as dbmod

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "slots.db"))
        await dbmod.init_db()
        now = datetime.utcnow()
        items = []
        # 韓国速報を大量に（より新しい時刻）
        for i in range(40):
            items.append(
                {
                    "title": f"한국 속보 테스트 {i} 삼성전자",
                    "url": f"https://example.com/kr/{i}",
                    "source": "Yonhap News Economy",
                    "summary": "kospi",
                    "guid": f"kr-{i}",
                    "region": "CN_ASIA",
                    "published": (now + timedelta(minutes=i)).strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    ),
                    "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        # US / JP は少し古いが窓内
        items.append(
            {
                "title": "NVDA jumps on AI demand in US markets today",
                "url": "https://example.com/us-1",
                "source": "CNBC Market News",
                "summary": "Nvidia AI",
                "guid": "us-1",
                "region": "US",
                "published": (now - timedelta(hours=2)).strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                ),
                "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        items.append(
            {
                "title": "日経平均が反発し半導体株が高い",
                "url": "https://example.com/jp-1",
                "source": "Yahoo Japan 経済・市況",
                "summary": "日経",
                "guid": "jp-1",
                "region": "JP",
                "published": (now - timedelta(hours=1)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        await dbmod.save_news(items)
        board = await dbmod.get_news_board(hours=18, limit=30, translate_ja=False)
        regions = {it["region"] for it in board["items"]}
        assert "US" in regions, board["items"][:5]
        assert "JP" in regions
        assert "CN_ASIA" in regions

    asyncio.run(_run())


def test_board_rank_newest_first():
    from app.core.news.database import rank_news_items_for_board

    items = [
        {
            "title": "Old NVDA story about earnings",
            "url": "https://example.com/old",
            "source": "CNBC Market News",
            "summary": "NVDA earnings",
            "published": "2026-08-10 10:00:00",
            "fetched_at": "2026-08-10 10:00:00",
        },
        {
            "title": "Fresh NVDA story about earnings",
            "url": "https://example.com/fresh",
            "source": "CNBC Market News",
            "summary": "NVDA earnings beat",
            "published": "2026-08-12 12:00:00",
            "fetched_at": "2026-08-12 12:00:00",
        },
        {
            "title": "Mid NVDA story about guidance",
            "url": "https://example.com/mid",
            "source": "CNBC Market News",
            "summary": "NVDA guidance",
            "published": "2026-08-11 15:00:00",
            "fetched_at": "2026-08-11 15:00:00",
        },
    ]
    ranked = rank_news_items_for_board(items, limit=10)
    urls = [r["url"] for r in ranked]
    assert urls.index("https://example.com/fresh") < urls.index("https://example.com/mid")
    assert urls.index("https://example.com/mid") < urls.index("https://example.com/old")


def test_board_drops_stale_republished_rss():
    """今日再取得された Jan 2025 記事が高スコアでも上に来ない。"""
    from app.core.news.database import (
        _parse_datetime_value,
        _board_content_datetime,
        rank_news_items_for_board,
    )

    assert _parse_datetime_value("Mon, 27 Jan 2025").year == 2025
    assert _parse_datetime_value("Mon, 27 Jan 2025 12:00:00 GMT").year == 2025

    stale = {
        "title": "Russia crude NVDA unrelated high score bait",
        "url": "https://example.com/stale-wsj",
        "source": "WSJ Markets",
        "summary": "oil sanctions Goldman",
        "published": "Mon, 27 Jan 2025",
        "fetched_at": "2026-08-12 04:58:50",
        "importance": 90,
    }
    # 公開日が古いまま fetched_at に落ちない
    assert _board_content_datetime(stale).year == 2025

    fresh = {
        "title": "Fresh NVDA AI financing story today",
        "url": "https://example.com/fresh-nvda",
        "source": "CNBC Market News",
        "summary": "Nvidia financing",
        "published": "Wed, 12 Aug 2026 06:01:00 GMT",
        "fetched_at": "2026-08-12 06:01:00",
    }
    ranked = rank_news_items_for_board([stale, fresh], limit=10, max_age_days=7)
    urls = [r["url"] for r in ranked]
    assert "https://example.com/stale-wsj" not in urls
    assert "https://example.com/fresh-nvda" in urls


def test_infer_region_from_feed_and_item():
    from app.core.news.region import infer_region, infer_region_from_feed

    assert infer_region_from_feed({"name": "Yahoo Japan 経済・市況", "url": "https://x"}) == "JP"
    assert infer_region_from_feed({"name": "CNBC Market News", "url": "https://x", "region": "US"}) == "US"
    assert infer_region_from_feed({"name": "Reuters", "url": "https://reuters.com/feed"}) == "GLOBAL"
    assert infer_region_from_feed({"name": "SCMP Business", "url": "https://scmp.com/rss"}) == "CN_ASIA"

    assert infer_region({"source": "SEC EDGAR 8-K", "title": "8-K filing", "url": "https://sec.gov/a"}) == "US"
    assert infer_region({"source": "x", "stock_codes": ["7203.T"], "title": "Toyota"}) == "JP"
    assert infer_region({"source": "x", "stock_codes": ["0700.HK"], "title": "Tencent"}) == "CN_ASIA"
    assert infer_region({"region": "japan", "title": "anything"}) == "JP"


def test_save_news_persists_region(tmp_path, monkeypatch):
    async def _run():
        import app.core.news.database as dbmod

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "news.db"))
        await dbmod.init_db()
        await dbmod.save_news(
            [
                {
                    "title": "JP market open",
                    "url": "https://example.com/jp-1",
                    "source": "Yahoo Japan 経済・市況",
                    "summary": "日経平均",
                    "guid": "jp-1",
                    "region": "JP",
                },
                {
                    "title": "US futures rise",
                    "url": "https://example.com/us-1",
                    "source": "CNBC Market News",
                    "summary": "S&P futures",
                    "guid": "us-1",
                    # region omitted → inferred from source
                },
            ]
        )
        board = await dbmod.get_news_board(hours=24, limit=20)
        regions = {it["url"]: it["region"] for it in board["items"]}
        # scoring may drop items without catalysts; check pool + counts instead
        pool = await dbmod.get_pool_news(hours=24, limit=50)
        by_url = {p["url"]: p for p in pool}
        assert by_url["https://example.com/jp-1"]["region"] == "JP"
        assert by_url["https://example.com/us-1"]["region"] == "US"
        assert board["region_counts"]["JP"] >= 1
        assert board["region_counts"]["US"] >= 1

        jp_only = await dbmod.get_news_board(hours=24, limit=20, region="JP")
        assert jp_only["region"] == "JP"
        assert all(it["region"] == "JP" for it in jp_only["items"])

    asyncio.run(_run())


def test_news_board_endpoint(tmp_path, monkeypatch):
    async def _seed():
        import app.core.news.database as dbmod

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "news_api.db"))
        await dbmod.init_db()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await dbmod.save_news(
            [
                {
                    "title": "Fed holds rates — NVDA reacts",
                    "url": "https://example.com/fed-nvda",
                    "source": "CNBC Market News",
                    "summary": "Federal Reserve holds rates; NVDA stock jumps on AI demand",
                    "guid": "fed-1",
                    "region": "US",
                    "fetched_at": now,
                },
                {
                    "title": "日経平均が反発、半導体株が高い",
                    "url": "https://example.com/nikkei-1",
                    "source": "Yahoo Japan 経済・市況",
                    "summary": "東京株式市場で日経平均が上昇",
                    "guid": "nikkei-1",
                    "region": "JP",
                    "fetched_at": now,
                },
            ]
        )

    asyncio.run(_seed())

    # Patch auth open + news DB path for the app import path
    import app.core.news.database as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "news_api.db"))

    with patch("app.core.auth._configured_token", return_value=""):
        from app.main import app

        client = TestClient(app)
        bad = client.get("/api/news/board?region=MARS")
        assert bad.status_code == 400

        res = client.get("/api/news/board?hours=24&limit=40")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "region_counts" in data
        assert "verdict" in data
        assert set(data["regions"]) >= {"US", "JP", "EU", "CN_ASIA", "GLOBAL"}
        assert data["region_counts"]["US"] >= 1
        assert data["region_counts"]["JP"] >= 1

        jp = client.get("/api/news/board?hours=24&region=JP")
        assert jp.status_code == 200
        assert jp.json()["region"] == "JP"
        assert all(i["region"] == "JP" for i in jp.json()["items"])


def test_run_news_ingest_once_saves(tmp_path, monkeypatch):
    async def _run():
        import app.core.news.database as dbmod
        from app.core.news.scheduler import run_news_ingest_once

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "ingest.db"))
        fake_items = [
            {
                "title": "Ingested US story about AAPL earnings beat",
                "url": "https://example.com/ingest-1",
                "source": "CNBC Market News",
                "summary": "Apple reports strong earnings",
                "guid": "ingest-1",
                "region": "US",
            }
        ]
        with patch(
            "app.core.news.fetcher.fetch_rss_on_demand",
            new_callable=AsyncMock,
            return_value=fake_items,
        ):
            stats = await run_news_ingest_once()
        assert stats["fetched"] == 1
        assert stats["inserted"] == 1
        assert await dbmod.count_pool() == 1

    asyncio.run(_run())


def test_ensure_fresh_pool_ingests_when_stale(tmp_path, monkeypatch):
    async def _run():
        import app.core.news.database as dbmod
        import app.core.news.scheduler as sched

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "stale.db"))
        monkeypatch.setattr(sched, "_last_ingest_at", 0.0)
        await dbmod.init_db()
        # 古い記事だけ → 直近18hは空
        await dbmod.save_news(
            [
                {
                    "title": "Stale story",
                    "url": "https://example.com/stale",
                    "source": "CNBC Market News",
                    "summary": "old",
                    "guid": "stale-1",
                    "region": "US",
                    "fetched_at": (datetime.utcnow() - timedelta(hours=40)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            ]
        )
        fake = [
            {
                "title": "Fresh AAPL catalyst story",
                "url": "https://example.com/fresh",
                "source": "CNBC Market News",
                "summary": "Apple earnings beat",
                "guid": "fresh-1",
                "region": "US",
            }
        ]
        with patch(
            "app.core.news.fetcher.fetch_rss_on_demand",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            stats = await sched.ensure_fresh_pool(hours=18, min_recent=5, force=False)
        assert stats["skipped"] is False, stats
        assert stats["inserted"] >= 1
        board = await dbmod.get_news_board(hours=18, limit=20)
        assert board["pool_scanned"] >= 1

    asyncio.run(_run())
