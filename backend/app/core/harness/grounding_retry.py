"""Grounding-quality retry / best-of-N without a second full tool loop."""
from __future__ import annotations

import os
import re

from app.utils.logger import get_logger

logger = get_logger(__name__)

_HARD_HINTS = re.compile(
    r"(なぜ|どうして|比較|vs\.?|versus|why|how did|どうだった|今日|today|"
    r"実装|直して|fix|bug|refactor|設計|なぜ動|終値|決算)",
    re.IGNORECASE,
)


def should_sample_hard(user_input: str, *, mode: str = "chat", has_search: bool = False) -> bool:
    """Heuristic: extra sample is worth it for hard chat/search turns."""
    if mode in ("task", "coding"):
        return False
    text = user_input or ""
    if has_search and _HARD_HINTS.search(text):
        return True
    if len(text) > 160 and has_search:
        return True
    return False


def sample_n(*, hard: bool) -> int:
    raw = os.environ.get("KAIRI_BEST_OF_N", "").strip()
    if raw.isdigit():
        n = int(raw)
        return max(1, min(n, 5))
    return 2 if hard else 1


def needs_grounding_retry(before: str, after: str) -> bool:
    """True when post-generation filters had to rewrite a lot of the draft."""
    pre = before or ""
    post = after or ""
    if not pre.strip() or not post.strip():
        return False
    drop = len(pre) - len(post)
    if drop > 60 and (drop / max(len(pre), 1)) > 0.20:
        return True
    try:
        from app.core.fact_filters.citation import get_last_citation_metrics

        metrics = get_last_citation_metrics()
        if int(getattr(metrics, "uncited_assertions", 0) or 0) >= 2:
            return True
    except Exception:
        pass
    return False


def candidate_score(raw: str, grounded: str) -> float:
    """Higher is better: keep information, minimize filter rewrites."""
    g = (grounded or "").strip()
    r = (raw or "").strip()
    if not g:
        return -1.0
    retention = len(g) / max(len(r), 1)
    retention = min(retention, 1.25)
    uncited = 0
    try:
        from app.core.fact_filters.citation import get_last_citation_metrics

        uncited = int(getattr(get_last_citation_metrics(), "uncited_assertions", 0) or 0)
    except Exception:
        pass
    return retention * 100.0 - uncited * 12.0


def pick_better_grounded(
    first_raw: str,
    first_grounded: str,
    alt_raw: str,
    alt_grounded: str,
) -> str:
    """Choose the grounded candidate with the better harness score."""
    a = candidate_score(first_raw, first_grounded)
    b = candidate_score(alt_raw, alt_grounded)
    if b > a + 1.0 and (alt_grounded or "").strip():
        logger.info("harness best-of-N: picked retry (%.1f > %.1f)", b, a)
        return alt_grounded
    return first_grounded


def retry_instruction() -> str:
    return (
        "【グラウンディング再生成】直前の草稿はソースに無い固有名または数値を含んでいた。"
        "検索結果の [n] に書いてあることだけを断定し、書けないことは省略せよ。"
        "XMLツールタグ・think・<<<FINAL_ANSWER>>> は禁止。本文だけ書け。"
    )
