"""Deterministic region tagging for news board (no LLM)."""
from __future__ import annotations

from typing import Any, Optional

# Canonical board regions
REGIONS = ("US", "JP", "EU", "CN_ASIA", "GLOBAL")

# Feed name / URL substrings → region (first match wins)
_FEED_RULES: list[tuple[str, str]] = [
    ("yahoo japan", "JP"),
    ("news.yahoo.co.jp", "JP"),
    ("日本株", "JP"),
    ("nikkei", "JP"),
    ("gl=jp", "JP"),
    ("ceid=jp", "JP"),
    ("yonhap", "CN_ASIA"),
    ("yna.co.kr", "CN_ASIA"),
    ("scmp", "CN_ASIA"),
    ("china", "CN_ASIA"),
    ("hong kong", "CN_ASIA"),
    ("sec edgar", "US"),
    ("sec.gov", "US"),
    ("pr newswire", "US"),
    ("businesswire", "US"),
    ("globenewswire", "US"),
    ("seeking alpha", "US"),
    ("wsj", "US"),
    ("cnbc", "US"),
    ("marketwatch", "US"),
    ("yahoo finance", "US"),
    ("investing.com", "US"),
    ("techcrunch", "US"),
    ("gl=us", "US"),
    ("ceid=us", "US"),
    ("reuters", "GLOBAL"),
    ("ap news", "GLOBAL"),
    ("apnews", "GLOBAL"),
]

_STOCK_SUFFIX = {
    ".T": "JP",
    ".JP": "JP",
    ".HK": "CN_ASIA",
    ".SS": "CN_ASIA",
    ".SZ": "CN_ASIA",
    ".KS": "CN_ASIA",
    ".KQ": "CN_ASIA",
    ".L": "EU",
    ".PA": "EU",
    ".DE": "EU",
    ".AS": "EU",
    ".MI": "EU",
    ".SW": "EU",
}


def normalize_region(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "ASIA": "CN_ASIA",
        "CN": "CN_ASIA",
        "HK": "CN_ASIA",
        "KR": "CN_ASIA",
        "CHINA": "CN_ASIA",
        "JAPAN": "JP",
        "USA": "US",
        "AMERICA": "US",
        "EUROPE": "EU",
        "WORLD": "GLOBAL",
        "WIRE": "GLOBAL",
        "OTHER": "GLOBAL",
    }
    key = aliases.get(key, key)
    return key if key in REGIONS else None


def infer_region_from_feed(feed: dict) -> str:
    """Prefer explicit feed['region'], else name/url heuristics."""
    explicit = normalize_region(feed.get("region"))
    if explicit:
        return explicit
    blob = f"{feed.get('name', '')} {feed.get('url', '')}".lower()
    for needle, region in _FEED_RULES:
        if needle in blob:
            return region
    return "GLOBAL"


def infer_region_from_stock_codes(stock_codes: Any) -> Optional[str]:
    if not stock_codes:
        return None
    codes = stock_codes
    if isinstance(codes, str):
        try:
            import json

            codes = json.loads(codes)
        except Exception:
            codes = [codes]
    if not isinstance(codes, (list, tuple)):
        return None
    for raw in codes:
        code = str(raw or "").upper()
        for suffix, region in _STOCK_SUFFIX.items():
            if code.endswith(suffix):
                return region
        # bare US tickers (AAPL) are weak signal — skip
    return None


def infer_region(item: dict) -> str:
    """Resolve region for a news item. Deterministic; never calls LLM."""
    explicit = normalize_region(item.get("region"))
    if explicit:
        return explicit

    from_stocks = infer_region_from_stock_codes(item.get("stock_codes"))
    if from_stocks:
        return from_stocks

    blob = f"{item.get('source', '')} {item.get('url', '')} {item.get('title', '')}".lower()
    for needle, region in _FEED_RULES:
        if needle in blob:
            return region

    # Japanese characters in title → JP bias
    title = item.get("title") or ""
    if any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in title[:80]):
        if any(k in blob for k in ("nikkei", "tokyo", "東証", "日経", "円安", "円高")):
            return "JP"

    return "GLOBAL"


def annotate_items_with_region(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in items:
        annotated = dict(item)
        annotated["region"] = infer_region(annotated)
        out.append(annotated)
    return out
