"""
無料の見出し英→日翻訳（LLM不使用）。

MyMemory Translation API（キー無し・短いテキスト向け）を使い、
結果は news.title_ja にキャッシュする。
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import quote

from app.utils.logger import get_logger

logger = get_logger(__name__)

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_TRANSLATE_TIMEOUT = 6.0
_MAX_CHARS = 450  # MyMemory の1リクエスト上限に余裕を持たせる


def looks_japanese(text: str) -> bool:
    if not text:
        return False
    return len(_CJK_RE.findall(text)) >= max(2, len(text) // 8)


def needs_ja_translation(title: str, title_ja: Optional[str] = None) -> bool:
    if title_ja and str(title_ja).strip():
        return False
    t = (title or "").strip()
    if not t or looks_japanese(t):
        return False
    # ほぼ ASCII / ラテン系なら翻訳候補
    return True


async def translate_en_to_ja(text: str) -> Optional[str]:
    """1文を英→日。失敗時は None。"""
    src = (text or "").strip()
    if not src:
        return None
    if looks_japanese(src):
        return src
    q = src[:_MAX_CHARS]
    url = (
        "https://api.mymemory.translated.net/get"
        f"?q={quote(q)}&langpair=en|ja"
    )
    try:
        from app.core.search.providers.http_client import get_http_client

        client = get_http_client()
        resp = await client.get(url, timeout=_TRANSLATE_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        translated = (
            ((data or {}).get("responseData") or {}).get("translatedText") or ""
        ).strip()
        if not translated:
            return None
        # MyMemory はクォータ超過時に英語のまま返すことがある
        if translated.lower() == q.lower():
            return None
        if "MYMEMORY WARNING" in translated.upper():
            return None
        return translated
    except Exception as e:
        logger.debug(f"translate_en_to_ja failed: {e}")
        return None


async def ensure_title_ja_for_items(
    items: list[dict],
    *,
    concurrency: int = 6,
    max_translate: int = 40,
) -> list[dict]:
    """
    ボード用アイテムに title_ja を付与。未キャッシュ分だけ翻訳して DB に保存。
    """
    from app.core.news.database import update_news_title_ja

    sem = asyncio.Semaphore(concurrency)
    pending: list[dict] = []
    for it in items:
        if needs_ja_translation(it.get("title") or "", it.get("title_ja")):
            pending.append(it)
        if len(pending) >= max_translate:
            break

    async def _one(it: dict) -> None:
        async with sem:
            ja = await translate_en_to_ja(it.get("title") or "")
            if not ja:
                return
            it["title_ja"] = ja
            news_id = it.get("id")
            if news_id is not None:
                try:
                    await update_news_title_ja(int(news_id), ja)
                except Exception as e:
                    logger.debug(f"title_ja persist failed id={news_id}: {e}")

    if pending:
        await asyncio.gather(*[_one(it) for it in pending], return_exceptions=True)

    # 日本語原文はそのまま title_ja にコピー（UI が title_ja 優先でも欠けない）
    for it in items:
        title = (it.get("title") or "").strip()
        if not (it.get("title_ja") or "").strip() and looks_japanese(title):
            it["title_ja"] = title
    return items
