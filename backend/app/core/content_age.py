"""
Content-Age Contract: keep transport time and observation time separate.

Two clocks:
  fetched_at     — when *we* pulled the payload (seed/transport age)
  content_as_of  — when the *observation* itself is from (content age)

A frozen upstream can look healthy on fetched_at while content_as_of is stale.
Never treat fetched_at as a substitute for published / content_as_of.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.isoformat() + "Z"
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    s = str(value).strip()
    return s or None


def stamp_quote_freshness(
    quote: dict[str, Any],
    *,
    content_as_of: Any = None,
    fetched_at: Any = None,
) -> dict[str, Any]:
    """Attach dual clocks to a quote dict. Does not invent content_as_of."""
    if not isinstance(quote, dict):
        return quote
    out = dict(quote)
    out["fetched_at"] = _to_iso(fetched_at) or out.get("fetched_at") or utc_now_iso()
    content = _to_iso(content_as_of)
    if content is None:
        content = _to_iso(out.get("content_as_of") or out.get("as_of"))
    if content is not None:
        out["content_as_of"] = content
    # previous_close_fallback is content-stale relative to a live session
    if out.get("price_kind") == "previous_close_fallback" and not out.get("content_stale"):
        out["content_stale"] = True
        out["content_stale_reason"] = "previous_close_fallback"
    return out


def result_content_time(item: dict[str, Any]) -> str:
    """Observation / publication time only — never falls back to fetch time."""
    for key in ("published", "pub_date", "published_at", "content_as_of", "date"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None and not isinstance(val, str):
            iso = _to_iso(val)
            if iso:
                return iso
    return ""


def result_fetch_time(item: dict[str, Any]) -> str:
    for key in ("fetched_at", "retrieved_at"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None and not isinstance(val, str):
            iso = _to_iso(val)
            if iso:
                return iso
    return ""


def format_source_clocks(item: dict[str, Any]) -> str:
    """Compact dual-clock label for prompt injection."""
    published = result_content_time(item)
    fetched = result_fetch_time(item)
    if published and fetched and published != fetched:
        return f"published: {published}; fetched_at: {fetched}"
    if published:
        return f"published: {published}"
    if fetched:
        return f"published: unknown; fetched_at: {fetched}"
    return "published: unknown"


def format_quote_clocks(quote: dict[str, Any], *, session_date: str = "") -> str:
    """Compact dual-clock fragment for market snapshot lines."""
    parts: list[str] = []
    content = quote.get("content_as_of") or quote.get("as_of")
    fetched = quote.get("fetched_at")
    if content:
        parts.append(f"content_as_of={content}")
    if fetched and fetched != content:
        parts.append(f"fetched_at={fetched}")
    if session_date:
        parts.append(f"session_date={session_date}")
    if quote.get("content_stale"):
        reason = quote.get("content_stale_reason") or "stale"
        parts.append(f"STALE_CONTENT({reason})")
    return " ".join(parts)
