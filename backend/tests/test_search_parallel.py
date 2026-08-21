import asyncio
import time
from unittest.mock import AsyncMock, patch


def test_independent_search_providers_overlap():
    from app.core.search.router import search

    async def slow_weather(_query):
        await asyncio.sleep(0.2)
        return [{"title": "tokyoの天気", "snippet": "ok", "url": "", "source": "open-meteo"}]

    async def slow_wiki(_query):
        await asyncio.sleep(0.2)
        return [{"title": "Wiki", "snippet": "ok", "url": "", "source": "wikipedia"}]

    async def _run():
        with patch("app.core.search.router._run_weather", new=AsyncMock(side_effect=slow_weather)), patch(
            "app.core.search.router._run_wikipedia", new=AsyncMock(side_effect=slow_wiki)
        ):
            t0 = time.perf_counter()
            results = await search("tokyo", providers=["weather", "wikipedia"])
            elapsed = time.perf_counter() - t0
            return results, elapsed

    results, elapsed = asyncio.run(_run())
    sources = {r.get("source") for r in results}
    assert "open-meteo" in sources
    assert "wikipedia" in sources
    # Sequential would be ~0.40s; overlap should finish well under that.
    assert elapsed < 0.35, elapsed
