"""
検索結果の単純リランカー（キーワード + 品質 + 鮮度 + 重複排除）
"""
from datetime import datetime
import re
from urllib.parse import urlparse
from app.utils.logger import get_logger

logger = get_logger(__name__)

HIGH_QUALITY_DOMAINS = {
    "reuters.com": 30.0,
    "bloomberg.com": 30.0,
    "nikkei.com": 30.0,
    "wsj.com": 30.0,
    "cnbc.com": 30.0,
    "ft.com": 30.0,
    "bloomberg.co.jp": 30.0,
    "jp.reuters.com": 30.0,
    "investing.com": 20.0,
    "finance.yahoo.com": 15.0,
    "bbc.com": 20.0,
    "cnn.com": 20.0,
    "nhk.or.jp": 20.0,
}

LOW_QUALITY_DOMAINS = {
    "yahoo.co.jp": -10.0,
    "msn.com": -10.0,
    "5ch.net": -30.0,
    "togetter.com": -20.0,
    "livedoor.jp": -15.0,
    "prtimes.jp": -5.0,
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _tokenize(text: str) -> set[str]:
    text_lower = text.lower()
    words = set(re.findall(r"[a-z0-9]+", text_lower))
    jp_chars = re.findall(r"[\u3040-\u9fff]+", text)
    for jp in jp_chars:
        for i in range(len(jp) - 1):
            words.add(jp[i : i + 2])
    return words


def _get_domain_score(url: str) -> float:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        for hq_domain, score in HIGH_QUALITY_DOMAINS.items():
            if domain == hq_domain or domain.endswith("." + hq_domain):
                return score
        for lq_domain, score in LOW_QUALITY_DOMAINS.items():
            if domain == lq_domain or domain.endswith("." + lq_domain):
                return score
    except Exception:
        pass
    return 0.0


def _calculate_jaccard_similarity(tokens1: set[str], tokens2: set[str]) -> float:
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union


def _age_points(age_days: int, weight: float) -> float:
    if 0 <= age_days <= 2:
        return 25.0 * weight
    if age_days <= 7:
        return 8.0 * weight
    if age_days > 30:
        return -20.0 * weight
    return -10.0 * weight


def _freshness_score(query: str, title: str, snippet: str) -> float:
    blob = f"{title} {snippet}"
    now = datetime.now()
    score = 0.0
    freshness_query = any(
        k in (query or "").lower()
        for k in ("今日", "本日", "today", "終値", "大引け", "市況", "close", "market")
    )
    weight = 1.5 if freshness_query else 1.0

    for m in re.finditer(r"(20\d{2})[年/\-](\d{1,2})[月/\-](\d{1,2})", blob):
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            score += _age_points((now - d).days, weight)
        except ValueError:
            pass

    for m in re.finditer(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(20\d{2})\b",
        blob,
        flags=re.IGNORECASE,
    ):
        try:
            mon = _MONTHS[m.group(1).lower()]
            d = datetime(int(m.group(3)), mon, int(m.group(2)))
            score += _age_points((now - d).days, weight)
        except ValueError:
            pass

    return max(-30.0, min(40.0, score))


def rerank(query: str, results: list[dict], top_k: int = 10, threshold: float = 0.0) -> list[dict]:
    if not results or len(results) <= 1:
        return results

    try:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return results[:top_k]

        scored = []
        for item in results:
            score = 0.0
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")

            title_tokens = _tokenize(title)
            snippet_tokens = _tokenize(snippet)
            url_tokens = _tokenize(url)

            score += len(query_tokens & title_tokens) * 10.0
            score += len(query_tokens & url_tokens) * 5.0
            score += len(query_tokens & snippet_tokens) * 2.0

            query_lower = query.lower()
            if query_lower in title.lower():
                score += 20.0
            if query_lower in snippet.lower():
                score += 10.0

            score += _get_domain_score(url)
            score += _freshness_score(query, title, snippet)
            scored.append((score, item, title_tokens | snippet_tokens))

        scored.sort(key=lambda x: x[0], reverse=True)

        deduplicated = []
        seen_tokens_list = []
        for score, item, item_tokens in scored:
            is_duplicate = False
            for seen_tokens in seen_tokens_list:
                if _calculate_jaccard_similarity(item_tokens, seen_tokens) > 0.6:
                    is_duplicate = True
                    break
            if not is_duplicate:
                deduplicated.append(item)
                seen_tokens_list.append(item_tokens)
            if len(deduplicated) >= top_k:
                break

        top_score = scored[0][0] if scored else 0
        logger.info(
            f"リランキング完了: {len(results)}件 → {len(deduplicated)}件 "
            f"(重複排除済) / 最高スコア: {top_score:.1f}"
        )
        return deduplicated

    except Exception as e:
        logger.error(f"リランキングに失敗しました: {e}")
        return results[:top_k]
