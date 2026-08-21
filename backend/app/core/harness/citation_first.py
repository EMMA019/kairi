"""Citation-first: extract source quotes before the model is allowed to invent."""
from __future__ import annotations

import re

from app.utils.logger import get_logger

logger = get_logger(__name__)

_BLOCK_RE = re.compile(
    r"\[(\d{1,3})\]\s*(?:\([^)]*\)\s*)?(?:\[[^\]]+\]\s*)?(.*?)(?=\n\[(?:\d{1,3})\]\s|\Z)",
    re.DOTALL,
)


def extract_grounded_quotes(source_text: str, *, max_quotes: int = 10) -> list[str]:
    """Turn numbered search blobs into short [n] quote lines the model may use."""
    src = (source_text or "").strip()
    if not src or "クエリに十分関連する情報は見つかりませんでした" in src:
        return []
    quotes: list[str] = []
    seen: set[str] = set()
    for m in _BLOCK_RE.finditer(src):
        n = m.group(1)
        body = " ".join((m.group(2) or "").split())
        body = re.sub(r"^⚠️[^\s]*\s*", "", body)
        body = re.sub(r"\s*URL:\s*\S+", "", body)
        body = body.strip(" -")
        if len(body) < 12:
            continue
        key = f"{n}:{body[:80]}"
        if key in seen:
            continue
        seen.add(key)
        if len(body) > 280:
            body = body[:277] + "…"
        quotes.append(f"- [{n}] {body}")
        if len(quotes) >= max_quotes:
            break
    return quotes


def build_citation_first_block(source_text: str) -> str:
    """Instruction prepended to executor context when search results exist."""
    quotes = extract_grounded_quotes(source_text)
    if not quotes:
        return ""
    return (
        "【引用ファースト・必須】使える事実は次だけ。本文はこの引用以外の固有名・数値を足すな。"
        "断定する文には根拠番号 [n] を付けよ。足りない事実は書くな（推測で埋めない）。\n"
        + "\n".join(quotes)
    )
