"""Free EN→JA title translation helpers (no LLM)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.news.translate import (
    looks_japanese,
    needs_ja_translation,
    translate_en_to_ja,
    ensure_title_ja_for_items,
)


def test_looks_japanese_and_needs():
    from app.core.news.translate import detect_langpair, looks_korean

    assert looks_japanese("日銀の利上げ観測")
    assert not looks_japanese("BOJ rate hike expectations")
    assert looks_korean("한국 속보 삼성전자")
    assert not looks_japanese("한국 속보 삼성전자")
    assert detect_langpair("BOJ rate hike expectations") == "en|ja"
    assert detect_langpair("한국 속보 삼성전자") == "ko|ja"
    assert needs_ja_translation("BOJ rate hike expectations", None)
    assert needs_ja_translation("한국 속보 삼성전자", None)
    assert not needs_ja_translation("BOJ rate hike", "日銀の利上げ")
    assert not needs_ja_translation("日経平均が反発", None)


def test_translate_en_to_ja_parses_mymemory():
    async def _run():
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "responseData": {"translatedText": "日銀の利上げ観測が高まる"}
        }
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        with patch(
            "app.core.search.providers.http_client.get_http_client",
            return_value=mock_client,
        ):
            out = await translate_en_to_ja("BOJ rate hike expectations grow")
        assert out == "日銀の利上げ観測が高まる"

    asyncio.run(_run())


def test_ensure_title_ja_skips_cached(tmp_path, monkeypatch):
    async def _run():
        import app.core.news.database as dbmod

        monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "tr.db"))
        await dbmod.init_db()
        await dbmod.save_news(
            [
                {
                    "title": "Tesla expands Japan delivery sites",
                    "url": "https://example.com/tesla-jp",
                    "source": "Nikkei Asia",
                    "summary": "x",
                    "guid": "t1",
                    "region": "JP",
                }
            ]
        )
        pool = await dbmod.get_pool_news(hours=24, limit=5)
        assert pool
        items = [dict(pool[0])]
        with patch(
            "app.core.news.translate.translate_to_ja",
            new_callable=AsyncMock,
            return_value="テスラが日本の納車拠点を拡大",
        ) as tr:
            await ensure_title_ja_for_items(items, max_translate=5)
            assert tr.await_count == 1
        assert "テスラ" in (items[0].get("title_ja") or "")
        # 2回目はキャッシュ済みなので呼ばない
        with patch(
            "app.core.news.translate.translate_to_ja",
            new_callable=AsyncMock,
            return_value="should-not-run",
        ) as tr2:
            # DB から読み直す
            pool2 = await dbmod.get_pool_news(hours=24, limit=5)
            items2 = [dict(pool2[0])]
            await ensure_title_ja_for_items(items2, max_translate=5)
            assert tr2.await_count == 0
            assert "テスラ" in (items2[0].get("title_ja") or "")

    asyncio.run(_run())
