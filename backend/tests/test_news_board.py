"""News Desk board: region tagging + /api/news/board data path."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


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
