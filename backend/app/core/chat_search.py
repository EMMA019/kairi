"""
チャット検索: carryover / clip / 実行 / 関連度不足時の拒否。
"""
from __future__ import annotations

import asyncio
import re
from typing import AsyncGenerator, Optional
from app.core.search import web_search
from app.core.search_relevance import (
    is_search_effectively_empty,
    SEARCH_UNSUPPORTED_PLACEHOLDER,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_SEARCH_CARRY_SESSIONS = 200
_last_search_by_session: dict[str, dict] = {}


def store_search_carryover(
    session_id: str,
    search_results_text: str | None,
    search_queries: list,
    user_input: str,
):
    """検索成功時にセッションへ結果を保存する。"""
    if not search_results_text or not search_results_text.strip():
        return
    if len(_last_search_by_session) >= _MAX_SEARCH_CARRY_SESSIONS and session_id not in _last_search_by_session:
        oldest_key = next(iter(_last_search_by_session))
        del _last_search_by_session[oldest_key]
    _last_search_by_session[session_id] = {
        "text": search_results_text,
        "queries": list(search_queries or []),
        "user_input": user_input,
    }


def maybe_carry_search_results(
    session_id: str,
    user_input: str,
    history_messages: list,
    search_needed: bool,
    search_results_text: str | None,
) -> str | None:
    """今ターン検索なしでも、直前ターンが検索済みかつ同一トピックなら結果を再注入する。"""
    if search_needed or search_results_text:
        return search_results_text
    prev = _last_search_by_session.get(session_id)
    if not prev or not prev.get("text"):
        return search_results_text

    stop = {
        "それ", "これ", "あれ", "どう", "そう", "けど", "だけど", "って", "感じ",
        "思う", "教えて", "ください", "です", "ます", "した", "いる", "ある",
        "だった", "よね", "なに", "何が", "the", "and", "was", "for", "about",
    }

    def _tokens(text: str) -> set[str]:
        found = set(re.findall(r"[一-龥ァ-ヶー]{2,}|[A-Za-z][A-Za-z0-9_\-]{2,}", text or ""))
        return {t for t in found if t.lower() not in stop and t not in stop}

    topic_tokens = _tokens(prev.get("user_input", ""))
    for q in prev.get("queries") or []:
        topic_tokens |= _tokens(str(q))
    if not topic_tokens:
        return search_results_text

    context_parts = [user_input or ""]
    for m in (history_messages or [])[-4:]:
        context_parts.append(str(m.get("content", ""))[:500])
    context = "\n".join(context_parts)

    overlap = [t for t in topic_tokens if t in context]
    if len(overlap) >= 1:
        logger.info(f"🔁 フォローアップへ前ターン検索結果を再注入 (overlap={overlap[:5]})")
        return prev["text"]
    return search_results_text


def clip_search_results(text: str, max_bytes: int = 100_000) -> str:
    if not text or len(text) <= max_bytes:
        return text
    logger.warning(f"⚠️ 検索結果が大きすぎます ({len(text):,} bytes) → {max_bytes:,} bytesにクリップ")
    half = max_bytes // 2
    return (
        text[:half]
        + f"\n\n[...検索結果が長すぎるため途中でカット ({len(text) - max_bytes} bytes削減)...]\n\n"
        + text[-half:]
    )


def extract_smart_snippet(text: str, max_chars: int = 15000) -> str:
    if not text or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 5
    tail = max_chars * 3 // 5
    return text[:head] + "\n\n[...中間セクション省略（トークン節約）...]\n\n" + text[-tail:]


def sanitize_conversational_query(q_text: str) -> str:
    if not q_text or len(q_text) <= 20:
        return q_text
    if any(k in q_text for k in ["半導体", "SOX", "200A", "2243", "AVGO"]) and any(
        k in q_text for k in ["銘柄", "組み込", "リバランス", "思惑", "狙い"]
    ):
        return "半導体株 ETF 注目銘柄 リバウンド 見通し 2026"
    if any(k in q_text for k in ["ポートフォリオ", "比率", "リバランス"]) and any(
        k in q_text for k in ["銘柄", "組み込", "おすすめ", "何がいい", "かな"]
    ):
        return "米国株 日本株 分散 高配当 ETF おすすめ 銘柄 2026"
    cleaned = re.sub(r"[ｗw！!？?。、,（）()]", " ", q_text)
    cleaned = re.sub(
        r"(?:だったんだ|なんだけど|だけど|思惑外れてる|外れてる|見ての通り|なので|から|ってこと|って|どう思う|いいと思う|いいかな|教えて|したい|しようと思ってます|思いますか|なんだよね|よね|だよね)",
        " ",
        cleaned,
    )
    tokens = [t for t in re.split(r"\s+", cleaned) if len(t) >= 2 and t not in ["今は", "けど", "なら", "なので"]]
    return " ".join(tokens[:5]) if tokens else q_text[:30]


def balance_search_queries(user_input: str, search_needed: bool, search_queries: list) -> tuple[bool, list]:
    """市場・ネガティブ問いに対するクエリバランス補完。"""
    market_keywords = [
        "暴落", "下落", "懸念", "株", "相場", "半導体", "インテル", "AVGO", "ブロードコム",
        "急落", "調整", "バブル", "SOX", "組み込", "リバランス", "銘柄", "ポートフォリオ", "ETF",
    ]
    negative_keywords = ["失敗", "問題", "危険", "批判", "欠点", "リスク", "悪化", "衰退", "デメリット", "バグ", "被害"]

    if any(kw in user_input for kw in market_keywords):
        search_needed = True
        if len(search_queries) == 1 and (
            len(search_queries[0]) > 30 or any(p in search_queries[0] for p in ["思惑", "短期", "見ての通り", "比率"])
        ):
            if any(k in user_input for k in ["半導体", "SOX", "SOXX", "インテル", "AVGO", "200A", "2243"]):
                search_queries[0] = "半導体株 ETF 見通し 動向 注目銘柄 2026"
            elif any(k in user_input for k in ["リバランス", "組み込", "ポートフォリオ", "高配当"]):
                search_queries[0] = "米国株 日本株 高配当 ETF おすすめ 注目銘柄 2026"

        has_rebound_query = any(
            w in q.lower() for q in search_queries for w in ["rebound", "recovery", "high", "反発", "回復", "見通し", "outlook"]
        )
        if not has_rebound_query and len(search_queries) < 2:
            if any(k in user_input for k in ["半導体", "SOX", "SOXX", "インテル", "AVGO", "200A", "2243"]):
                search_queries.append("semiconductor ETF stock market outlook 2026")
            else:
                search_queries.append("US Japan stock dividend ETF market outlook 2026")
            logger.info(f"📈 市場調査クエリにバランス反発・見通し検索クエリを自動追加しました: {search_queries[-1]}")
    elif search_needed and any(kw in user_input for kw in negative_keywords) and len(search_queries) < 2:
        search_queries.append(f"{search_queries[0]} solutions improvements latest update 2026")
        logger.info(f"⚖️ リサーチクエリに多角的バランス補完クエリを追加しました: {search_queries[-1]}")

    return search_needed, search_queries


async def run_web_search(
    *,
    user_input: str,
    search_queries: list,
    search_providers: list,
) -> AsyncGenerator[dict, None]:
    """
    検索を実行し、SSE用イベント dict を yield。
    最後に {"type": "_result", "text": ..., "sources": ...} を返す。
    """
    search_results_text = None
    search_sources: list = []
    tasks = []
    max_queries = 2
    for q in search_queries[:max_queries]:
        yield {"type": "status", "status": "searching", "query": q}
        yield {"type": "pipeline", "stage": "search", "detail": f"情報収集中: {q}"}
        tasks.append(web_search(q, providers=search_providers))
        logger.info(f"検索実行: '{q}' (Providers: {search_providers}) (Original: '{user_input}')")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_raw_sources = []
    direct_url_fallback_texts = []
    for i, res in enumerate(results):
        q = search_queries[i]
        if isinstance(res, Exception):
            logger.error(f"検索実行エラー '{q}': {res}")
        else:
            text, sources = res
            if "URL (" in text and "の内容:" in text:
                direct_url_fallback_texts.append(text)
            all_raw_sources.extend(sources)

    combined_texts = list(direct_url_fallback_texts)
    if all_raw_sources:
        from app.core.search.reranker import rerank
        from app.core.search.formatter import format_for_prompt
        from app.core.source_evaluator import evaluate_source_authority
        from app.core.search.router import fetch_url

        global_top_sources = rerank(user_input, all_raw_sources, top_k=20)

        deep_fetched_text = ""
        for src in global_top_sources:
            url = src.get("url", "")
            title = src.get("title", "")
            source_label = src.get("source", "")
            eval_res = evaluate_source_authority(url, title, source_label)

            if eval_res["tier"] == 1 and url:
                logger.info(f"🚀 Tier 1 記事の本文取得(ディープフェッチ)実行: {url} (Title: {title})")
                yield {"type": "status", "status": "scraping_promotion", "url": url}
                try:
                    scraped_content = await fetch_url(url)
                    if scraped_content and not scraped_content.startswith("❌") and len(scraped_content.strip()) > 50:
                        content_snippet = extract_smart_snippet(scraped_content, 15000)
                        deep_fetched_text = f"【Tier 1記事 本文抽出: {title} ({url})】\n{content_snippet}\n\n"
                        break
                except Exception as e:
                    logger.warning(f"Tier 1記事の本文取得失敗 {url}: {e}")

        global_text = format_for_prompt(global_top_sources, user_input)
        combined_texts.append(f"【統合検索結果（関連度トップ20件）】\n{global_text}")
        if deep_fetched_text:
            combined_texts.append(deep_fetched_text)
        search_sources = global_top_sources

    if combined_texts:
        search_results_text = clip_search_results("\n\n".join(combined_texts))

    if search_sources:
        unique_sources = []
        seen_urls = set()
        for s in search_sources:
            if s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                unique_sources.append(s)
        search_sources = unique_sources
        yield {"type": "sources", "data": search_sources}

    yield {"type": "_result", "text": search_results_text, "sources": search_sources}


def finalize_search_context(
    *,
    session_id: str,
    user_input: str,
    messages: list,
    search_needed: bool,
    search_queries: list,
    search_results_text: Optional[str],
    direct_url_texts: list[str] | None = None,
) -> tuple[Optional[str], bool]:
    """
    URL本文統合・carryover・実質空判定・carryover保存。
    Returns: (search_results_text, search_unsupported)
    """
    if direct_url_texts:
        existing_text = search_results_text or ""
        search_results_text = clip_search_results(existing_text + "\n\n" + "\n\n".join(direct_url_texts))
        logger.info("ユーザー指定URLのスクレイピング本文をコンテキストに統合完了")

    if not search_results_text:
        search_results_text = maybe_carry_search_results(
            session_id, user_input, messages, search_needed, search_results_text
        )

    search_unsupported = False
    if search_needed:
        if is_search_effectively_empty(user_input, search_queries, search_results_text):
            search_unsupported = True
            search_results_text = SEARCH_UNSUPPORTED_PLACEHOLDER
            logger.warning("🚫 検索結果が実質空のため推測禁止プレースホルダに置換")

    if search_results_text and not search_unsupported:
        store_search_carryover(session_id, search_results_text, search_queries, user_input)

    return search_results_text, search_unsupported
