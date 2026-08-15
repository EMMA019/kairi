"""Thin persistent completion-gate / resume contract."""
from __future__ import annotations

from app.core.goal_state import (
    DEFAULT_MAX_GOAL_ROUNDS,
    PHASE_BLOCKED,
    PHASE_COMPLETED,
    REASON_ACCEPTANCE,
    REASON_BUILD,
    REASON_LOOP_CAP,
    REASON_UNVERIFIED,
    format_resume_instruction,
    is_blocked,
    latest_goal,
    persist_gate,
    phase_from_gate,
    reasons_from_gate,
    remaining_rounds,
)
from app.core.chat_orchestrator import is_continuation_utterance


def test_reasons_from_gate_codes():
    gate = {
        "ok": False,
        "verdict": "fail",
        "acceptance": {"failed_ids": ["file_exists:README"]},
        "build": {"success": False, "exit_code": 1, "skipped": False},
    }
    reasons = reasons_from_gate(gate, hit_loop_cap=True)
    assert REASON_LOOP_CAP in reasons
    assert REASON_ACCEPTANCE in reasons
    assert REASON_BUILD in reasons
    assert phase_from_gate(gate, hit_loop_cap=True) == PHASE_BLOCKED


def test_unverified_is_blocked_not_completed():
    gate = {"ok": True, "verdict": "unverified", "acceptance": {}, "build": {"skipped": True, "success": True}}
    assert phase_from_gate(gate) == PHASE_BLOCKED
    assert REASON_UNVERIFIED in reasons_from_gate(gate)


def test_pass_is_completed():
    gate = {
        "ok": True,
        "verdict": "pass",
        "acceptance": {"failed_ids": []},
        "build": {"success": True},
    }
    assert phase_from_gate(gate) == PHASE_COMPLETED
    assert reasons_from_gate(gate) == []


def test_persist_and_resume_instruction(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    sid = "goal-resume-1"
    gate = {
        "ok": False,
        "verdict": "fail",
        "acceptance": {"failed_ids": ["accept-jump"]},
        "build": {"success": False, "exit_code": 1, "skipped": False},
    }
    persist_gate(
        sid,
        gate,
        hit_loop_cap=True,
        mode="task",
        user_input="JUMPゲームを実装して",
    )
    goal = latest_goal(sid)
    assert is_blocked(goal)
    assert goal["mode"] == "task"
    assert "accept-jump" in goal["failed_ids"]
    assert goal["rounds_used"] >= 1
    text = format_resume_instruction(goal)
    assert "永続ゴール・再開" in text
    assert "accept-jump" in text
    assert "Build NG" in text
    assert is_continuation_utterance("続きを作成して")


def test_session_budget_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    sid = "goal-budget-1"
    fail = {
        "ok": False,
        "verdict": "fail",
        "acceptance": {"failed_ids": ["x"]},
        "build": {"success": True, "skipped": True},
    }
    prev = None
    for _ in range(DEFAULT_MAX_GOAL_ROUNDS):
        prev = persist_gate(sid, fail, mode="task", user_input="x", prev=prev)
    goal = latest_goal(sid)
    assert remaining_rounds(goal) == 0
    text = format_resume_instruction(goal)
    assert "ゴール予算切れ" in text


def test_completed_resets_rounds(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    sid = "goal-done-1"
    fail = {
        "ok": False,
        "verdict": "fail",
        "acceptance": {"failed_ids": ["x"]},
        "build": {"success": True, "skipped": True},
    }
    persist_gate(sid, fail, mode="task", user_input="x")
    persist_gate(
        sid,
        {"ok": True, "verdict": "pass", "acceptance": {}, "build": {"success": True}},
        mode="task",
        user_input="x",
    )
    goal = latest_goal(sid)
    assert goal["phase"] == PHASE_COMPLETED
    assert goal["rounds_used"] == 0
    assert not is_blocked(goal)
