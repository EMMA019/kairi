"""
Detect syndicated / reprinted headlines so they don't inflate source diversity.

Same PR Newswire story appearing on Yahoo / CNBC / MarketWatch must not look
like three independent confirmations.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SOURCE_SUFFIX_RE = re.compile(
    r"\s*[-–—|]\s*(?:reuters|ap|bloomberg|cnbc|marketwatch|yahoo|"
    r"wsj|nikkei|seeking alpha|business wire|pr newswire|globenewswire)\s*$",
    re.IGNORECASE,
)


def normalize_headline(title: str) -> str:
    t = (title or "").strip().lower()
    t = _SOURCE_SUFFIX_RE.sub("", t)
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def content_fingerprint(item: dict[str, Any]) -> str:
    """
    Stable fingerprint over normalized title (+ short summary stem).
    Empty title → empty fingerprint (caller should skip).
    """
    title = normalize_headline(str(item.get("title") or ""))
    if not title:
        return ""
    summary = _WS_RE.sub(" ", str(item.get("summary") or item.get("snippet") or "")).strip().lower()
    summary = _PUNCT_RE.sub(" ", summary)
    summary = _WS_RE.sub(" ", summary).strip()[:160]
    payload = title if not summary else f"{title}\n{summary}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def annotate_syndication(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    First occurrence of a fingerprint stays independent; later ones are syndicated.

    Preference order among a group: high-trust first (if already scored), else
    input order. Mutates copies — does not alter the original list objects'
    identity beyond returning new dicts.
    """
    if not items:
        return []

    # Prefer high-trust / higher importance as the canonical independent copy
    ordered = sorted(
        enumerate(items),
        key=lambda pair: (
            0 if pair[1].get("is_high_trust_source") else 1,
            -(pair[1].get("importance") or 0),
            pair[0],
        ),
    )

    seen: dict[str, int] = {}
    tagged: list[Optional[dict[str, Any]]] = [None] * len(items)

    for orig_i, item in ordered:
        out = dict(item)
        fp = content_fingerprint(out)
        out["content_fingerprint"] = fp
        if not fp:
            out["independence"] = "unknown"
            tagged[orig_i] = out
            continue
        if fp in seen:
            out["independence"] = "syndicated"
            out["syndicated_of"] = seen[fp]
        else:
            out["independence"] = "independent"
            seen[fp] = orig_i
        tagged[orig_i] = out

    return [t for t in tagged if t is not None]


def demote_syndicated(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Annotate syndication, then soft-demote syndicated copies in ranking order.
    Independent items keep their scores; syndicated get importance *= 0.35.
    """
    annotated = annotate_syndication(items)
    for it in annotated:
        if it.get("independence") == "syndicated":
            base = it.get("importance") or 0
            it["importance"] = max(1, int(base * 0.35)) if base else 0
            it["syndicated"] = True
    annotated.sort(
        key=lambda x: (
            0 if x.get("independence") == "independent" else 1,
            -(x.get("importance") or 0),
            0 if x.get("is_high_trust_source") else 1,
        )
    )
    return annotated
