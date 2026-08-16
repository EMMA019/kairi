"""
検索結果が「実質空」（件数ゼロ or クエリ関連度不足）かを判定する。

関連の薄いヒットを「結果あり」と誤認して事実断定を許さないための軽量ヒューリスティック。
追加 LLM は使わない。
"""
from __future__ import annotations

import re
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 関連トークン重なり率の下限（これ未満は実質空）
DEFAULT_MIN_OVERLAP_RATIO = 0.18
DEFAULT_MIN_HIT_TOKENS = 1

_STOP = {
    "それ", "これ", "あれ", "どう", "そう", "けど", "だけど", "って", "感じ",
    "思う", "教えて", "ください", "です", "ます", "した", "いる", "ある",
    "だった", "よね", "なに", "何が", "について", "お願い", "して",
    "the", "and", "was", "for", "about", "with", "from", "that", "this",
    "what", "who", "when", "where", "how", "into", "http", "https", "www",
    "検索", "結果", "情報", "最新", "詳細",
}

_EMPTY_MARKERS = [
    "結果は見つかりません",
    "見つかりませんでした",
    "no results",
    "0件",
    "クエリに十分関連する情報は見つかりませんでした",
]


SEARCH_UNSUPPORTED_INSTRUCTION = (
    "【重要・検索結果不足】検索では質問に十分関連する情報を確認できませんでした。"
    "固有名・数値・役職・順位・結果などの事実を、推測や学習知識で埋めてはいけません。"
    "「検索結果からは確認できませんでした」と明確に伝えてください。"
)

SEARCH_UNSUPPORTED_PLACEHOLDER = (
    "【検索結果】クエリに十分関連する情報は見つかりませんでした。"
    "事実の断定・固有名の補完は禁止です。"
)


def _tokens(text: str) -> set[str]:
    found = set(re.findall(r"[一-龥ァ-ヶー]{2,}|[A-Za-z][A-Za-z0-9_\-]{2,}", text or ""))
    out = set()
    for t in found:
        tl = t.lower()
        if tl in _STOP or t in _STOP:
            continue
        if len(t) < 2:
            continue
        out.add(t)
        out.add(tl)
    return out


def query_result_overlap_ratio(
    user_input: str,
    search_queries: list | None,
    results_text: str,
) -> tuple[float, int, int]:
    """
    クエリ語が結果本文にどれだけ含まれるか。
    Returns: (ratio, hit_count, token_count)
    """
    q_tokens: set[str] = set()
    q_tokens |= _tokens(user_input or "")
    for q in search_queries or []:
        q_tokens |= _tokens(str(q))
    # 表記ゆれ用に lower のみのセットへ
    norms = {t.lower() for t in q_tokens if len(t) >= 2}
    if not norms:
        return 1.0, 0, 0  # 判定不能→空扱いにしない

    body = (results_text or "").lower()
    hits = sum(1 for t in norms if t in body)
    ratio = hits / max(len(norms), 1)
    return ratio, hits, len(norms)


def is_search_effectively_empty(
    user_input: str,
    search_queries: list | None,
    results_text: str | None,
    *,
    min_overlap_ratio: float = DEFAULT_MIN_OVERLAP_RATIO,
    min_hit_tokens: int = DEFAULT_MIN_HIT_TOKENS,
) -> bool:
    """
    検索必須ターンで、結果を「根拠として使えない」とみなすか。
    """
    text = (results_text or "").strip()
    if not text:
        return True

    lower = text.lower()
    if any(m.lower() in lower for m in _EMPTY_MARKERS) and len(text) < 400:
        return True

    # プレースホルダのみ
    if text.startswith("【検索結果】クエリに十分関連"):
        return True

    ratio, hits, n_tok = query_result_overlap_ratio(user_input, search_queries, text)
    if n_tok == 0:
        return False
    if hits < min_hit_tokens or ratio < min_overlap_ratio:
        logger.info(
            f"📉 検索結果の関連度不足: hits={hits}/{n_tok} ratio={ratio:.2f} "
            f"(min_hits={min_hit_tokens}, min_ratio={min_overlap_ratio})"
        )
        return True
    return False


_MARKET_SOURCE_NOISE_RE = re.compile(
    r"日経|ロイター|Reuters|ZAi|ザイ|ストップ高|注目株|株式市場|"
    r"ダイヤモンド.?ザイ|日本株市場|daily.?zai|finance\.yahoo|"
    r"\b8-K\b|sec\.gov|\bEDGAR\b|sec filing|"
    r"premarket|biggest moves|is up more than|"
    r"Goldman|JPMorgan|Sandisk",
    re.IGNORECASE,
)
_FINANCE_QUERY_RE = re.compile(
    r"株|銘柄|株価|相場|配当|決算|投資|市況|日経|ダウ|ナスダック|為替|金利|"
    r"\bstocks?\b|\bearnings\b|\bnasdaq\b|\bdow\b",
    re.IGNORECASE,
)


def drop_offtopic_market_sources(user_input: str, sources: list) -> list:
    """非市況クエリから、日経・ロイター・ZAi などの市況ヒットを除く。"""
    if not sources:
        return sources
    text = user_input or ""
    if _FINANCE_QUERY_RE.search(text):
        return sources
    kept = []
    for src in sources:
        blob = f"{src.get('title') or ''} {src.get('url') or ''} {src.get('source') or ''}"
        if _MARKET_SOURCE_NOISE_RE.search(blob):
            logger.info(f"🧹 非市況クエリから市況ソースを除外: {src.get('title') or src.get('url')}")
            continue
        kept.append(src)
    return kept if kept else sources


_NEWS_BRIEFING_RE = re.compile(
    r"ニュース|報道|速報|ヘッドライン|\bnews\b|\bheadlines?\b|what happened",
    re.IGNORECASE,
)
_OUTING_EXPLICIT_RE = re.compile(
    r"イベント|祭り|花火|お出かけ|おでかけ|観光|ワークショップ|展示|"
    r"\bevents?\b|\bfestival\b|\bfireworks\b",
    re.IGNORECASE,
)
_EVENT_ROUNDUP_NOISE_RE = re.compile(
    r"イベントまとめ|おでかけ|お出かけ|週末イベント|週末占い|九星|気学|"
    r"花火まとめ|おすすめおでかけ|開催される.?イベント|"
    r"sortiraparis|weekend events?|kids events this weekend|"
    r"無料または低料金のお出かけ",
    re.IGNORECASE,
)


def is_explicit_outing_query(user_input: str) -> bool:
    return bool(_OUTING_EXPLICIT_RE.search(user_input or ""))


def is_news_briefing_query(user_input: str) -> bool:
    """『ニュース教えて』系。イベント明示や市況は対象外。"""
    text = user_input or ""
    if not _NEWS_BRIEFING_RE.search(text):
        return False
    if is_explicit_outing_query(text):
        return False
    if _FINANCE_QUERY_RE.search(text):
        return False
    return True


def is_japanese_majority_query(user_input: str) -> bool:
    text = user_input or ""
    cjk = len(re.findall(r"[一-龥ぁ-んァ-ン]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return cjk >= 2 and cjk >= latin


def news_briefing_search_queries(user_input: str, *, now_jst=None) -> list[str]:
    """日本語ニュースは日本、英語ニュースは世界。『今週末』はクエリに使わない。"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = now_jst or datetime.now(ZoneInfo("Asia/Tokyo"))
    date_iso = now.strftime("%Y-%m-%d")
    month_en = now.strftime("%B")
    day = now.day
    year = now.year
    if is_japanese_majority_query(user_input):
        return [
            f"日本 主要ニュース {date_iso}",
            f"今週 日本 ニュース 速報",
            f"Japan news {month_en} {day} {year}",
        ]
    return [
        f"world news {month_en} {day} {year}",
        f"international headlines {date_iso}",
        f"global news this week",
    ]


def drop_offtopic_event_sources(user_input: str, sources: list) -> list:
    """ニュース質問から、地域イベントまとめ・占い・お出かけ記事を除く。"""
    if not sources or not is_news_briefing_query(user_input):
        return sources
    kept = []
    for src in sources:
        blob = f"{src.get('title') or ''} {src.get('url') or ''} {src.get('source') or ''}"
        if _EVENT_ROUNDUP_NOISE_RE.search(blob):
            logger.info(f"🧹 ニュース質問からイベントまとめを除外: {src.get('title') or src.get('url')}")
            continue
        kept.append(src)
    return kept
