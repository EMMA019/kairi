"""Canonical numbered source list for prompt, Sources panel, and citation checks."""
from __future__ import annotations

from typing import Any


def _url_key(url: str) -> str:
    return (url or "").strip()


class SourceIndex:
    """URL-deduped sources with stable 1-based [n] used everywhere."""

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []
        self._by_url: dict[str, int] = {}

    def max_n(self) -> int:
        return len(self._items)

    def items(self) -> list[dict[str, Any]]:
        return list(self._items)

    def as_ui_list(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for s in self._items:
            row: dict[str, Any] = {
                "title": s.get("title") or s.get("url") or "",
                "url": s.get("url") or "",
                "n": s.get("n"),
            }
            if s.get("tier") is not None:
                row["tier"] = s["tier"]
            rows.append(row)
        return rows

    def add(self, sources: list[dict] | None) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        for raw in sources or []:
            if not isinstance(raw, dict):
                continue
            url = _url_key(str(raw.get("url") or ""))
            if not url or url in self._by_url:
                continue
            n = len(self._items) + 1
            item = dict(raw)
            item["url"] = url
            item["n"] = n
            self._items.append(item)
            self._by_url[url] = n
            added.append(item)
        return added

    def drop_trailing(self, keep: int) -> None:
        keep = max(0, int(keep))
        self._items = self._items[:keep]
        self._by_url = {_url_key(str(s.get("url") or "")): int(s["n"]) for s in self._items}

    def format_for_prompt(self, query: str = "") -> str:
        from app.core.search.formatter import format_for_prompt

        return format_for_prompt(self._items, query)

    def ingest_hits(self, sources: list[dict] | None, query: str = "") -> str:
        """Add hits and return a prompt block numbered with global [n]."""
        from app.core.search.formatter import format_for_prompt

        added = self.add(sources)
        if not added:
            return ""
        return format_for_prompt(added, query, include_contract=False)
