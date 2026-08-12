"""
無料の見出し→日本語翻訳（LLM不使用）。

MyMemory Translation API（キー無し・短いテキスト向け）を使い、
結果は news.title_ja にキャッシュする。英語・韓国語に対応。
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import quote

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ひらがな・カタカナ・漢字（日本語判定用。ハングルは含めない）
_JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_TRANSLATE_TIMEOUT = 6.0
_MAX_CHARS = 450


def looks_japanese(text: str) -> bool:
    """かなを含む、または漢字が多くハングルが無いとき日本語とみなす。"""
    if not text:
        return False
    if _HANGUL_RE.search(text):
        return False
    kana = len(re.findall(r"[\u3040-\u30ff]", text))
    if kana >= 2:
        return True
    return len(_JA_RE.findall(text)) >= max(3, len(text) // 6)


def looks_korean(text: str) -> bool:
    if not text:
        return False
    return len(_HANGUL_RE.findall(text)) >= 2


def detect_langpair(text: str) -> Optional[str]:
    """MyMemory の langpair（source|ja）。翻訳不要なら None。"""
    t = (text or "").strip()
    if not t or looks_japanese(t):
        return None
    if looks_korean(t):
        return "ko|ja"
    if _LATIN_RE.search(t):
        return "en|ja"
    # 漢字のみ（中国語の可能性）→ zh-CN|ja
    if _JA_RE.search(t) and not _HANGUL_RE.search(t):
        return "zh-CN|ja"
    return "en|ja"


def needs_ja_translation(title: str, title_ja: Optional[str] = None) -> bool:
    if title_ja and str(title_ja).strip():
        return False
    return detect_langpair(title) is not None


async def translate_to_ja(text: str, langpair: Optional[str] = None) -> Optional[str]:
    """1文を日本語へ。失敗時は None。"""
    src = (text or "").strip()
    if not src:
        return None
    if looks_japanese(src):
        return src
    pair = langpair or detect_langpair(src)
    if not pair:
        return None
    q = src[:_MAX_CHARS]
    url = (
        "https://api.mymemory.translated.net/get"
        f"?q={quote(q)}&langpair={quote(pair)}"
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
        if translated.lower() == q.lower():
            return None
        if "MYMEMORY WARNING" in translated.upper():
            return None
        return translated
    except Exception as e:
        logger.debug(f"translate_to_ja failed ({pair}): {e}")
        return None


# 後方互換エイリアス
async def translate_en_to_ja(text: str) -> Optional[str]:
    return await translate_to_ja(text, "en|ja")


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
            title = it.get("title") or ""
            ja = await translate_to_ja(title)
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

    for it in items:
        title = (it.get("title") or "").strip()
        if not (it.get("title_ja") or "").strip() and looks_japanese(title):
            it["title_ja"] = title
    return items
