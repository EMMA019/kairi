"""Completion-gate helpers for task/coding runs."""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_GATE_REINJECT = 3


def extract_spec_internal(*prompt_blobs: str) -> Optional[str]:
    blob = "\n".join(p or "" for p in prompt_blobs)
    m = re.search(
        r"<spec_internal>\n?(.*?)\n?</spec_internal>",
        blob,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def run_task_completion_gate(
    workspace: str,
    *,
    spec_internal: Optional[str] = None,
) -> dict[str, Any]:
    from app.core.build_gate import run_completion_gate

    return run_completion_gate(workspace, spec_internal=spec_internal)


def gate_reinject_message(meta: dict) -> str:
    from app.core.acceptance_checker import AcceptanceReport

    acc = meta.get("acceptance_report")
    build = meta.get("build") or {}
    parts = [
        "【システム完了ゲート・未達】完了宣言は禁止。次を満たしてから再出力すること。\n",
    ]
    if isinstance(acc, AcceptanceReport):
        parts.append(acc.format_for_agent())
    else:
        failed = (meta.get("acceptance") or {}).get("failed_ids") or []
        if failed:
            parts.append("Acceptance NG: " + ", ".join(failed))
    if not build.get("success") and not build.get("skipped"):
        parts.append(
            f"\nBuild NG (exit={build.get('exit_code')}):\n"
            f"```\n{(build.get('output') or '')[-1500:]}\n```\n"
            "ワークスペースルートでビルドが通るまで修正すること。"
        )
    parts.append(
        "\n未達項目だけを <file>/<replace> で直し、再度ビルドが通る状態にすること。"
    )
    return "\n".join(parts)


def append_final_gate_banner(
    response: str,
    gate: dict[str, Any],
    *,
    hit_loop_cap: bool,
    yield_sse_func: Optional[Callable[[dict], Any]] = None,
) -> str:
    """Append incomplete/unverified banners after the main loop."""
    if not gate.get("ok"):
        from app.core.acceptance_checker import format_incomplete_banner

        banner = format_incomplete_banner(
            gate.get("acceptance_report"),
            gate.get("build"),
            hit_loop_cap=hit_loop_cap,
        )
        response += banner
        acc = gate.get("acceptance_report")
        if acc and hasattr(acc, "format_for_agent"):
            response += "\n\n" + acc.format_for_agent()
        if yield_sse_func:
            yield_sse_func({
                "type": "status",
                "status": "incomplete",
                "detail": "completion_gate",
                "acceptance": gate.get("acceptance"),
                "build_ok": (gate.get("build") or {}).get("success"),
            })
    elif gate.get("verdict") == "unverified":
        from app.core.acceptance_checker import format_unverified_banner

        response += format_unverified_banner()
        if yield_sse_func:
            yield_sse_func({
                "type": "status",
                "status": "unverified",
                "detail": "completion_gate_no_checks",
            })
    return response
