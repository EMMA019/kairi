"""
Named prompt assembly (dsh PromptSection / PromptContext inspired).

Static sections are prefix-stable: changing one named section moves one hash.
Dynamic contexts (clock, KV, skills, entities) never enter the static hash or
the supervisor LLM cache key.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Union

TextValue = Union[str, Callable[[], str]]


@dataclass(frozen=True)
class PromptSection:
    """Immutable / prefix-stable system prompt layer."""

    name: str
    order: int
    text: TextValue


@dataclass(frozen=True)
class PromptContext:
    """Per-turn dynamic context (clock, KV, skills, entities, ...)."""

    name: str
    order: int
    text: TextValue


def _resolve(value: TextValue) -> str:
    if callable(value):
        return str(value() or "")
    return str(value or "")


class PromptAssembly:
    """Named registry for static sections + dynamic contexts."""

    def __init__(self) -> None:
        self._sections: dict[str, PromptSection] = {}
        self._contexts: dict[str, PromptContext] = {}

    def section(self, section: PromptSection) -> None:
        self._sections[section.name] = section

    def context(self, context: PromptContext) -> None:
        self._contexts[context.name] = context

    def register_section(self, name: str, order: int, text: TextValue) -> None:
        self.section(PromptSection(name=name, order=order, text=text))

    def register_context(self, name: str, order: int, text: TextValue) -> None:
        self.context(PromptContext(name=name, order=order, text=text))

    def list_sections(self) -> list[PromptSection]:
        return sorted(self._sections.values(), key=lambda s: (s.order, s.name))

    def list_contexts(self) -> list[PromptContext]:
        return sorted(self._contexts.values(), key=lambda c: (c.order, c.name))

    def render_static(self) -> str:
        parts = [_resolve(s.text).strip() for s in self.list_sections()]
        return "\n\n".join(p for p in parts if p)

    def render_dynamic(self) -> str:
        parts = [_resolve(c.text).strip() for c in self.list_contexts()]
        return "\n\n".join(p for p in parts if p)

    def static_hash(self) -> str:
        return hash_static_prompt(self.render_static())

    def snapshot(self) -> dict:
        return {
            "sections": [
                {"name": s.name, "order": s.order, "chars": len(_resolve(s.text))}
                for s in self.list_sections()
            ],
            "contexts": [
                {"name": c.name, "order": c.order, "chars": len(_resolve(c.text))}
                for c in self.list_contexts()
            ],
            "static_hash": self.static_hash(),
        }


def hash_static_prompt(static_prompt: str) -> str:
    """Stable MD5 of static prompt text only (never dynamic context)."""
    return hashlib.md5((static_prompt or "").encode("utf-8")).hexdigest()


def join_named(parts: Iterable[tuple[str, str]]) -> str:
    blocks = []
    for name, text in parts:
        t = (text or "").strip()
        if t:
            blocks.append(t)
    return "\n\n".join(blocks)
