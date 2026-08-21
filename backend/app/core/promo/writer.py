"""Turn telemetry into a post draft. No invented stats, no engagement bait."""
from __future__ import annotations

from typing import Any


DISCLOSURE = (
    "Posted by the Kairi promo scheduler from this machine's telemetry. "
    "Not an ad network; own channel only."
)
DISCLOSURE_JA = (
    "この投稿は Kairi の宣伝スケジューラが、このマシンのテレメトリだけから下書きしたものです。"
    "他人の投稿へのリプライはしません。"
)


def _line(label: str, value: Any) -> str | None:
    if value is None or value == "" or value == 0 or value == 0.0:
        return None
    return f"- {label}: {value}"


def draft_from_metrics(metrics: dict[str, Any], *, disclose_bot: bool = True, locale: str = "en") -> dict[str, str]:
    version = metrics.get("app_version") or "?"
    ja = (locale or "en").startswith("ja")
    title = (
        f"Kairi {version} — local grounding telemetry"
        if not ja
        else f"Kairi {version} — ローカル grounding テレメトリ"
    )

    lines: list[str] = []
    if disclose_bot:
        lines.append(DISCLOSURE_JA if ja else DISCLOSURE)
        lines.append("")

    intro = (
        "Numbers below are from this install (filters, Integrity, latency). "
        "Missing sources are omitted — nothing here is estimated."
        if not ja
        else "以下はこのインストールの実測です（フィルタ・Integrity・レイテンシ）。欠けている項目は書いていません。"
    )
    lines.append(intro)
    lines.append("")

    bullets: list[str] = []
    bullets.append(_line("version", version))
    bullets.append(_line("eval cases in tree", metrics.get("eval_case_count")))
    bullets.append(_line("grounding filter text-changes", metrics.get("filter_total_changes")))
    hits = metrics.get("filter_hits") or {}
    if isinstance(hits, dict) and hits:
        top = ", ".join(f"{k}×{v}" for k, v in list(hits.items())[:5])
        bullets.append(f"- top filters: {top}")
    bullets.append(_line("verified facts (Integrity)", metrics.get("verified_facts")))
    bullets.append(_line("citations (Integrity)", metrics.get("citations")))
    bullets.append(_line("search executions", metrics.get("search_executions")))
    bullets.append(_line("violations logged (7d)", metrics.get("violation_count_7d")))
    types = metrics.get("violation_types_7d") or {}
    if isinstance(types, dict) and types:
        top_v = ", ".join(f"{k}×{v}" for k, v in list(types.items())[:5])
        bullets.append(f"- violation types: {top_v}")
    if metrics.get("ttft_p50_ms") is not None:
        bullets.append(f"- TTFT p50 (first chunk): {metrics['ttft_p50_ms']} ms")
    if metrics.get("ttft_p95_ms") is not None:
        bullets.append(f"- TTFT p95: {metrics['ttft_p95_ms']} ms")
    if metrics.get("supervisor_skip_rate") is not None:
        rate = float(metrics["supervisor_skip_rate"])
        bullets.append(f"- supervisor skip rate: {rate:.0%}")
    if metrics.get("latency_sample_count"):
        bullets.append(f"- latency samples: {metrics['latency_sample_count']}")

    used = [b for b in bullets if b]
    if len(used) <= 1:
        used.append("- (no other telemetry yet — draft held for a later collect)")
    lines.extend(used)
    lines.append("")
    lines.append(
        "Repo: grounded local BYOK chat. Citation / content-age / numeric defense. "
        "https://github.com/EMMA019/kairi"
        if not ja
        else "リポジトリ: グラウンディング付きローカル BYOK チャット。"
        " 引用・content-age・数値防御。 https://github.com/EMMA019/kairi"
    )

    body = "\n".join(lines).strip()
    if len(body) > 1800:
        body = body[:1790].rstrip() + "…"
    return {"title": title, "body": body}
