"""
Thin persistent completion-gate state (dsh-goal inspired, not a full goal machine).

Persists the latest gate verdict as append-only `goal/change` events so
「続きを作成して」 can resume from the same blockers instead of a new request.

Phases: active | blocked | completed
Reason codes (policy-owned): acceptance_ng | build_ng | loop_cap | unverified
"""
from __future__ import annotations

from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

PHASE_ACTIVE = "active"
PHASE_BLOCKED = "blocked"
PHASE_COMPLETED = "completed"

REASON_ACCEPTANCE = "acceptance_ng"
REASON_BUILD = "build_ng"
REASON_LOOP_CAP = "loop_cap"
REASON_UNVERIFIED = "unverified"

DEFAULT_MAX_GOAL_ROUNDS = 6  # blocked *runs* across continuations (not per-turn reinjects)


def reasons_from_gate(
    gate: Optional[dict[str, Any]],
    *,
    hit_loop_cap: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if hit_loop_cap:
        reasons.append(REASON_LOOP_CAP)
    gate = gate or {}
    acc = gate.get("acceptance") if isinstance(gate.get("acceptance"), dict) else {}
    if acc.get("failed_ids"):
        reasons.append(REASON_ACCEPTANCE)
    build = gate.get("build") if isinstance(gate.get("build"), dict) else {}
    if build and not build.get("success") and not build.get("skipped"):
        reasons.append(REASON_BUILD)
    if gate.get("verdict") == "unverified" and REASON_ACCEPTANCE not in reasons and REASON_BUILD not in reasons:
        reasons.append(REASON_UNVERIFIED)
    return reasons


def phase_from_gate(
    gate: Optional[dict[str, Any]],
    *,
    hit_loop_cap: bool = False,
) -> str:
    if hit_loop_cap:
        return PHASE_BLOCKED
    gate = gate or {}
    if gate.get("verdict") == "unverified":
        return PHASE_BLOCKED
    if gate.get("ok"):
        return PHASE_COMPLETED
    return PHASE_BLOCKED


def is_blocked(goal: Optional[dict[str, Any]]) -> bool:
    return bool(goal) and goal.get("phase") == PHASE_BLOCKED


def remaining_rounds(goal: Optional[dict[str, Any]]) -> int:
    if not goal:
        return DEFAULT_MAX_GOAL_ROUNDS
    used = int(goal.get("rounds_used") or 0)
    cap = int(goal.get("max_rounds") or DEFAULT_MAX_GOAL_ROUNDS)
    return max(0, cap - used)


def latest_goal(session_id: str) -> Optional[dict[str, Any]]:
    if not (session_id or "").strip():
        return None
    from app.core.session_events import read_events

    events = read_events(session_id, types=["goal/change"])
    if not events:
        return None
    payload = events[-1].get("payload") or {}
    return dict(payload) if isinstance(payload, dict) else None


def record_goal_change(
    session_id: str,
    *,
    phase: str,
    reasons: Optional[list[str]] = None,
    gate: Optional[dict[str, Any]] = None,
    mode: str = "",
    user_input: str = "",
    rounds_used: int = 0,
    max_rounds: int = DEFAULT_MAX_GOAL_ROUNDS,
) -> dict[str, Any]:
    from app.core.session_events import append_event, truncate_text

    gate = gate or {}
    acc = gate.get("acceptance") if isinstance(gate.get("acceptance"), dict) else {}
    build = gate.get("build") if isinstance(gate.get("build"), dict) else {}
    payload = {
        "phase": phase,
        "reasons": list(reasons or []),
        "verdict": gate.get("verdict"),
        "failed_ids": list(acc.get("failed_ids") or []),
        "build_ok": bool(build.get("success")) if build else None,
        "build_exit": build.get("exit_code"),
        "build_skipped": bool(build.get("skipped")),
        "mode": mode or "",
        "user_input": truncate_text(user_input or "", 500),
        "rounds_used": int(rounds_used),
        "max_rounds": int(max_rounds),
    }
    append_event(session_id, "goal/change", payload)
    logger.info(
        "goal/change session=%s phase=%s reasons=%s rounds=%s/%s",
        session_id[:16],
        phase,
        payload["reasons"],
        payload["rounds_used"],
        payload["max_rounds"],
    )
    return payload


def persist_gate(
    session_id: str,
    gate: Optional[dict[str, Any]],
    *,
    hit_loop_cap: bool = False,
    mode: str = "",
    user_input: str = "",
    prev: Optional[dict[str, Any]] = None,
    rounds_delta: int = 1,
) -> dict[str, Any]:
    """Write a goal/change from this run's gate. Increment session blocked-run budget."""
    prev = prev if prev is not None else latest_goal(session_id)
    phase = phase_from_gate(gate, hit_loop_cap=hit_loop_cap)
    reasons = reasons_from_gate(gate, hit_loop_cap=hit_loop_cap)
    used = int((prev or {}).get("rounds_used") or 0)
    cap = int((prev or {}).get("max_rounds") or DEFAULT_MAX_GOAL_ROUNDS)
    if phase == PHASE_BLOCKED:
        used = used + max(1, int(rounds_delta))
    elif phase == PHASE_COMPLETED:
        used = 0
    return record_goal_change(
        session_id,
        phase=phase,
        reasons=reasons,
        gate=gate,
        mode=mode,
        user_input=user_input,
        rounds_used=used,
        max_rounds=cap,
    )


def format_resume_instruction(goal: dict[str, Any]) -> str:
    """Model-visible resume block for a blocked goal."""
    reasons = goal.get("reasons") or []
    failed = goal.get("failed_ids") or []
    lines = [
        "【永続ゴール・再開】直前の完了ゲートは未達のまま残っています。",
        "新しい依頼として解釈せず、未達項目だけを直して再開すること。",
        f"phase: {goal.get('phase')}",
        f"reasons: {', '.join(reasons) or '(none)'}",
        f"rounds_used: {goal.get('rounds_used', 0)}/{goal.get('max_rounds', DEFAULT_MAX_GOAL_ROUNDS)}",
    ]
    if failed:
        lines.append("Acceptance NG: " + ", ".join(str(x) for x in failed[:12]))
    if goal.get("build_ok") is False and not goal.get("build_skipped"):
        lines.append(f"Build NG (exit={goal.get('build_exit')})")
    if remaining_rounds(goal) <= 0:
        lines.append(
            "【ゴール予算切れ】同じ修正の自動再試行は禁止。"
            "残っているブロッカーを説明し、方針を変えるかユーザー確認を取ること。"
        )
    orig = (goal.get("user_input") or "").strip()
    if orig:
        lines.append("元の依頼（抜粋）:\n" + orig[:400])
    return "\n".join(lines)
