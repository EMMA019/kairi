"""
チャット検索: carryover / clip / 実行 / 関連度不足時の拒否。
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone, timedelta
from typing import AsyncGenerator, Literal, Optional
from zoneinfo import ZoneInfo

from app.core.search import web_search
from app.core.search_relevance import (
    is_search_effectively_empty,
    SEARCH_UNSUPPORTED_PLACEHOLDER,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_SEARCH_CARRY_SESSIONS = 200
_last_search_by_session: dict[str, dict] = {}
JST = timezone(timedelta(hours=9))
ET = ZoneInfo("America/New_York")

_TODAYISH_KW = (
    "今日",
    "本日",
    "大引け",
    "終値",
    "today",
    "どうだった",
    "どう動",
    "前場",
    "後場",
    "寄り",
    "昼休み",
    "どんな感じ",
)


def parse_explicit_calendar_date(
    text: str,
    *,
    default_year: int | None = None,
) -> date | None:
    """文中の 7/29・7月29日・2026-07-29 を抽出。なければ None。"""
    if not text:
        return None
    now = datetime.now(JST)
    year_default = default_year if default_year is not None else now.year
    m = re.search(r"(?:(\d{4})[年/\-])?(\d{1,2})[月/\-](\d{1,2})日?", text)
    if not m:
        return None
    year = int(m.group(1)) if m.group(1) else year_default
    try:
        return date(year, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _previous_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def last_us_equity_session_date(now_jst: datetime | None = None) -> date:
    """
    直近の米国株レギュラーセッション確定日（ET）。
    平日 16:00 ET 未満 → 前営業日、以降 → 当日（土日は金曜へ）。
    """
    now = now_jst or datetime.now(JST)
    et = now.astimezone(ET)
    d = et.date()
    if d.weekday() >= 5:
        return _previous_weekday(d)
    if et.hour < 16:
        return _previous_weekday(d)
    return d


def resolve_market_anchor_date(
    user_input: str,
    *,
    market: Literal["jp", "us"] = "jp",
    now_jst: datetime | None = None,
) -> date:
    """
    市況クエリの日付アンカー。
    明示日付があればそれを優先。なければ日本=JST今日、米国=直近確定セッション日。
    """
    now = now_jst or datetime.now(JST)
    explicit = parse_explicit_calendar_date(user_input, default_year=now.year)
    if explicit:
        return explicit
    if market == "us":
        return last_us_equity_session_date(now)
    return now.date()


def format_anchor_date_en(d: date) -> str:
    """July 29, 2026 形式。"""
    return d.strftime("%B %d, %Y").replace(" 0", " ")


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


def _is_todayish_market_query(user_input: str, *, now_jst: datetime | None = None) -> bool:
    """今日系キーワード、または明示日付付き市況質問を日付正規化対象にする。"""
    text = user_input or ""
    if any(k in text for k in _TODAYISH_KW):
        return True
    return parse_explicit_calendar_date(text) is not None


def balance_search_queries(user_input: str, search_needed: bool, search_queries: list) -> tuple[bool, list]:
    """市場・ネガティブ問いに対するクエリバランス補完（地域スコープ付き）。"""
    now_jst = datetime.now(JST)
    jp_anchor = resolve_market_anchor_date(user_input, market="jp", now_jst=now_jst)
    us_anchor = resolve_market_anchor_date(user_input, market="us", now_jst=now_jst)
    today_jp = jp_anchor.isoformat()
    today_us = us_anchor.isoformat()
    today_us_en = format_anchor_date_en(us_anchor)

    market_keywords = [
        "暴落", "下落", "懸念", "株", "相場", "市場", "半導体", "インテル", "AVGO", "ブロードコム",
        "急落", "調整", "バブル", "SOX", "組み込", "リバランス", "銘柄", "ポートフォリオ", "ETF",
        "日経", "ダウ", "ナスダック", "TOPIX", "金融", "セクター", "業種",
        "前場", "後場",
    ]
    negative_keywords = ["失敗", "問題", "危険", "批判", "欠点", "リスク", "悪化", "衰退", "デメリット", "バグ", "被害"]

    jp_scope = any(
        k in user_input
        for k in ("日本市場", "日経", "東証", "TOPIX", "東京株式", "日本株", "国内市場")
    )
    us_scope = any(
        k in user_input
        for k in ("米国市場", "アメリカ市場", "NY", "ナスダック", "Nasdaq", "S&P", "ダウ", "Dow", "Wall Street", "米国株")
    )
    todayish = _is_todayish_market_query(user_input, now_jst=now_jst)
    # planner と同じ: 「今日の市場」単独は日本寄り
    if todayish and not jp_scope and not us_scope and any(
        k in user_input for k in ("市場", "相場", "market", "Market")
    ):
        jp_scope = True
    sector_finance = any(k in user_input for k in ("金融", "銀行", "保険", "証券"))
    sector_semi = any(k in user_input for k in ("半導体", "SOX", "電機"))
    wants_topix = "TOPIX" in user_input or "トピックス" in user_input
    wants_sector = any(k in user_input for k in ("セクター", "業種", "ローテーション")) or sector_finance or sector_semi

    if any(kw in user_input for kw in market_keywords) or jp_scope or us_scope:
        search_needed = True

        # 今日系の日本/米国は地域特化クエリに正規化（最大4本）
        # 明示日付（例: 7/29）があればその日を使い、JST今日で上書きしない
        if todayish and jp_scope and not us_scope:
            from app.core.market_session import get_jp_session_bucket, jp_cash_price_query_word

            price_word = jp_cash_price_query_word(now_jst)
            # 過去日の明示質問は終値記事が正しい
            explicit = parse_explicit_calendar_date(user_input)
            if explicit is not None and jp_anchor < now_jst.date():
                price_word = "終値"
            search_queries = [
                f"日経平均 {price_word} {today_jp}",
                f"東京株式市場 市況 {today_jp}",
                f"TOPIX {price_word} {today_jp}",
                f"業種別騰落率 東証 {today_jp}",
            ]
            if get_jp_session_bucket(now_jst) == "closed" and now_jst.hour >= 16:
                search_queries[3] = f"日経225先物 夜間取引 {today_jp}"
            logger.info(f"🇯🇵 日本市場今日系クエリに正規化: {search_queries}")
            return search_needed, search_queries[:4]

        if todayish and us_scope and not jp_scope:
            search_queries = [
                f"US stock market {today_us_en}",
                f"Dow S&P Nasdaq close {today_us}",
            ]
            logger.info(f"🇺🇸 米国市場今日系クエリに正規化: {search_queries}")
            return search_needed, search_queries[:2]

        # 日本市場フォロー（金融/TOPIX/セクター）— 今日でなくても補強
        soft_jp = jp_scope or (sector_finance and not us_scope) or (wants_sector and not us_scope and "ローテーション" in user_input)
        if soft_jp and not us_scope and (wants_topix or wants_sector or sector_finance):
            extras = []
            if wants_topix or wants_sector:
                extras.append(f"TOPIX 終値 騰落 {today_jp}")
            if sector_finance or wants_sector:
                extras.append(f"東証 業種別騰落 銀行 保険 {today_jp}")
            if sector_semi:
                extras.append(f"半導体 関連株 騰落 東京市場 {today_jp}")
            merged = list(search_queries or [])
            for e in extras:
                if e not in merged:
                    merged.append(e)
            search_queries = merged[:4]
            logger.info(f"🇯🇵 日本市場フォロークエリ補強: {search_queries}")
            return search_needed, search_queries

        if len(search_queries) == 1 and (
            len(search_queries[0]) > 30 or any(p in search_queries[0] for p in ["思惑", "短期", "見ての通り", "比率"])
        ):
            if any(k in user_input for k in ["半導体", "SOX", "SOXX", "インテル", "AVGO", "200A", "2243"]):
                search_queries[0] = "半導体株 ETF 見通し 動向 注目銘柄 2026"
            elif any(k in user_input for k in ["リバランス", "組み込", "ポートフォリオ", "高配当"]):
                if jp_scope and not us_scope:
                    search_queries[0] = "日本株 高配当 ETF おすすめ 注目銘柄 2026"
                elif us_scope and not jp_scope:
                    search_queries[0] = "US dividend ETF stock picks outlook 2026"
                else:
                    search_queries[0] = "米国株 日本株 高配当 ETF おすすめ 注目銘柄 2026"

        has_rebound_query = any(
            w in q.lower()
            for q in search_queries
            for w in ["rebound", "recovery", "high", "反発", "回復", "見通し", "outlook", "終値", "close", "TOPIX", "業種"]
        )
        if not has_rebound_query and len(search_queries) < 2:
            if any(k in user_input for k in ["半導体", "SOX", "SOXX", "インテル", "AVGO", "200A", "2243"]):
                search_queries.append("semiconductor ETF stock market outlook 2026")
            elif jp_scope and not us_scope:
                search_queries.append(f"日経平均 市況 見通し {today_jp}")
            elif us_scope and not jp_scope:
                search_queries.append(f"US stock market outlook {today_us}")
            else:
                search_queries.append("US Japan stock dividend ETF market outlook 2026")
            logger.info(f"📈 市場調査クエリに補完クエリを追加: {search_queries[-1]}")
    elif search_needed and any(kw in user_input for kw in negative_keywords) and len(search_queries) < 2:
        search_queries.append(f"{search_queries[0]} solutions improvements latest update 2026")
        logger.info(f"⚖️ リサーチクエリに多角的バランス補完クエリを追加しました: {search_queries[-1]}")

    return search_needed, search_queries


def should_skip_deep_fetch(user_input: str) -> bool:
    """終値・大引け・今日の市況はスニペットで足りるのでディープフェッチ省略。"""
    text = user_input or ""
    if parse_explicit_calendar_date(text) and any(
        k in text for k in ("市場", "市況", "前場", "後場", "終値", "どうだった", "どんな感じ")
    ):
        return True
    return any(
        k in text
        for k in (
            "終値",
            "大引け",
            "今日の日本市場",
            "今日の米国市場",
            "本日の市場",
            "市況",
            "前場",
            "後場",
        )
    )


def _format_us_market_snapshot_for_prompt(user_input: str = "") -> str:
    """米国主要指数の確定値ブロック（Yahoo）。検索より優先してハルシネーションを防ぐ。"""
    from app.core.tools.market_data import _quotes_batch

    tickers = [
        ("DIA", "ダウ (DIA)"),
        ("SPY", "S&P500 (SPY)"),
        ("QQQ", "ナスダック100 (QQQ)"),
        ("SOXX", "半導体 SOXX"),
    ]
    anchor = resolve_market_anchor_date(user_input, market="us")
    batch = _quotes_batch([t for t, _ in tickers], prefer_yfinance=True, enrich_vol_atr=False)
    quotes = (batch or {}).get("quotes") or {}
    src = (batch or {}).get("source") or "yfinance"
    lines = [
        f"【米国市場スナップショット anchor={anchor.isoformat()} source={src}（推測禁止・この数値を優先）】",
        "※ 個別セッション終値の歴史値が無い場合は直近取得値。日付記事と食い違う場合は記事の日付を優先し、ここは参考とする。",
    ]
    for ticker, label in tickers:
        q = quotes.get(ticker) or {}
        price = q.get("current_price")
        chg = q.get("change")
        pct = q.get("change_pct")
        if price is None:
            lines.append(f"- {label}: 取得失敗")
            continue
        parts = [f"{float(price):,.2f}"]
        if chg is not None and pct is not None:
            sign = "+" if chg >= 0 else ""
            parts.append(f"{sign}{chg:,.2f}（{sign}{pct:.2f}%）")
        lines.append(f"- {label}: {' '.join(parts)}")
    return "\n".join(lines)


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
    # 日本市況は TOPIX/業種クエリを含めて最大4本
    qblob = " ".join(search_queries or [])
    jp_market = any(
        k in (user_input or "")
        for k in ("日本市場", "日経", "東証", "TOPIX", "東京株式", "日本株", "国内市場")
    ) or any(k in qblob for k in ("日経", "TOPIX", "東証", "東京株式"))
    us_market = any(
        k in (user_input or "")
        for k in ("米国市場", "アメリカ市場", "NY", "ナスダック", "Nasdaq", "S&P", "ダウ", "Dow", "Wall Street", "米国株")
    ) or any(k in qblob.lower() for k in ("dow", "nasdaq", "s&p", "us stock"))
    max_queries = 4 if jp_market else 2
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

    # 日本/米国市況: yfinance スナップショットを検索より先に置く（推測禁止の確定値）
    snapshot_block = ""
    if jp_market:
        try:
            from app.core.tools.market_data import format_jp_market_snapshot_for_prompt
            snapshot_block = format_jp_market_snapshot_for_prompt(user_input)
        except Exception as e:
            logger.warning(f"JP market snapshot failed: {e}")
    elif us_market:
        try:
            snapshot_block = _format_us_market_snapshot_for_prompt(user_input)
        except Exception as e:
            logger.warning(f"US market snapshot failed: {e}")

    combined_texts = list(direct_url_fallback_texts)
    if snapshot_block:
        combined_texts.insert(0, snapshot_block)
    if all_raw_sources:
        from app.core.search.reranker import rerank
        from app.core.search.formatter import format_for_prompt
        from app.core.source_evaluator import evaluate_source_authority
        from app.core.search.router import fetch_url

        global_top_sources = rerank(user_input, all_raw_sources, top_k=20)

        deep_fetched_text = ""
        skip_deep = should_skip_deep_fetch(user_input)
        if skip_deep:
            logger.info("⏩ 市場終値/今日系のため Tier1 ディープフェッチをスキップ")
        for src in global_top_sources:
            if skip_deep:
                break
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

    # IBKR 口座照会: 検索の有無に関係なくスナップショットを先頭注入
    try:
        from app.core.ibkr.intent import prepend_ibkr_snapshot

        search_results_text = prepend_ibkr_snapshot(user_input, search_results_text)
    except Exception as e:
        logger.warning(f"IBKR snapshot inject failed: {e}")

    return search_results_text, search_unsupported
