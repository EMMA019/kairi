#!/usr/bin/env python3
"""
Kairi 評価ハーネス（オフライン）。

使い方（backend/ から）:
  python -m evals.run_evals
  python evals/run_evals.py

LLM は呼ばず、mock_executor_output + fact_filters / carryover、
または scripted mock LLM → 本物 loop/grounding/SSE（assembled_loop）で判定する。
"""
from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML が必要です: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# backend/ をパスに
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases() -> list[dict[str, Any]]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data:
            data["_path"] = str(path.name)
            cases.append(data)
    return cases


def apply_fact_filters(text: str, source: str, user_input: str = "") -> str:
    from app.core.fact_filters.pipeline import apply_grounding_pipeline
    return apply_grounding_pipeline(text, source or "", user_input or "")


_TERMINALS = set("。．！？!?…‼⁉」』）)]\"'”’")


def ends_with_terminal(text: str) -> bool:
    s = (text or "").rstrip()
    if not s:
        return True
    if s.endswith("```"):
        return True
    return s[-1] in _TERMINALS


def check_expectations(text: str, exp: dict, *, carryover_ok: bool | None = None) -> list[str]:
    failures = []
    if exp.get("ends_with_terminal") and not ends_with_terminal(text):
        failures.append(f"ends_with_terminal: got ending {text[-20]!r}")
    for s in exp.get("must_not_contain") or []:
        if s in text:
            failures.append(f"must_not_contain failed: {s!r} found")
    for s in exp.get("must_contain") or []:
        if s not in text:
            failures.append(f"must_contain failed: {s!r} missing")
    any_list = exp.get("must_contain_any") or []
    if any_list and not any(s in text for s in any_list):
        failures.append(f"must_contain_any failed: none of {any_list}")
    pat = exp.get("must_not_match")
    if pat and re.search(pat, text):
        failures.append(f"must_not_match failed: {pat}")
    for name in exp.get("forbid_uncited_proper_nouns") or []:
        if name in text:
            failures.append(f"forbid_uncited_proper_nouns: {name!r} still present")
    if exp.get("carryover_injected") is True and carryover_ok is not True:
        failures.append("carryover_injected expected True")
    if exp.get("carryover_injected") is False and carryover_ok is True:
        failures.append("carryover_injected expected False")
    golden = exp.get("golden_output")
    if golden is not None:
        expected = str(golden).rstrip()
        actual = (text or "").rstrip()
        if actual != expected:
            failures.append(
                f"golden_output mismatch: expected_len={len(expected)} actual_len={len(actual)}"
            )
    return failures


def run_carryover(case: dict) -> tuple[str, bool]:
    from app.routers.chat import (
        _store_search_carryover,
        _maybe_carry_search_results,
        _last_search_by_session,
    )
    fx = case.get("carryover_fixture") or {}
    sid = fx.get("session_id", "eval")
    _last_search_by_session.pop(sid, None)
    _store_search_carryover(
        sid,
        fx.get("prev_text", ""),
        fx.get("prev_queries") or [],
        fx.get("prev_user_input", ""),
    )
    carried = _maybe_carry_search_results(
        sid,
        case.get("input", ""),
        case.get("history") or [],
        search_needed=False,
        search_results_text=None,
    )
    _last_search_by_session.pop(sid, None)
    ok = carried is not None and bool(str(carried).strip())
    return str(carried or ""), ok



def run_assembled_loop(case: dict) -> tuple[str, dict]:
    """Scripted mock LLM through real chat loop + grounding + SSE (keyless)."""
    import asyncio
    import uuid
    from app.core.eval_support.llm_replay import run_assembled_loop_snapshot
    from app.core import session_events as se

    sid = f"eval-assembled-{uuid.uuid4().hex[:10]}"
    tmp = Path(__file__).resolve().parent / "_tmp_session_events"
    tmp.mkdir(parents=True, exist_ok=True)
    prev_dir = se.SESSION_EVENTS_DIR
    se.SESSION_EVENTS_DIR = tmp
    try:
        result = asyncio.run(
            run_assembled_loop_snapshot(
                user_input=case.get("input") or "",
                mock_executor_output=case.get("mock_executor_output") or "",
                search_results=case.get("search_results") or "",
                session_id=sid,
            )
        )
    finally:
        se.SESSION_EVENTS_DIR = prev_dir
        # cleanup this session file only
        path = tmp / f"{sid}.jsonl"
        if path.exists():
            path.unlink()
    return result["final_text"], result


def run_case(case: dict) -> tuple[bool, str, list[str]]:
    import os

    pipeline = case.get("pipeline", "fact_filters_only")
    exp = case.get("expectations") or {}
    carryover_ok = None
    fake_today = (case.get("fake_today") or "").strip()
    prev_fake = os.environ.get("KAIRI_FAKE_TODAY")
    try:
        if fake_today:
            os.environ["KAIRI_FAKE_TODAY"] = fake_today
        if pipeline == "carryover_only":
            text, carryover_ok = run_carryover(case)
        elif pipeline == "assembled_loop":
            text, assembled = run_assembled_loop(case)
            # SSE + session event contract checks
            sse_types = {e.get("type") for e in assembled.get("sse_events") or []}
            for t in exp.get("sse_must_include_types") or []:
                if t not in sse_types:
                    # defer into failures via synthetic expectation below
                    exp = dict(exp)
                    exp.setdefault("_assembled_failures", []).append(f"sse missing type {t!r}")
            sess_types = {e.get("type") for e in assembled.get("session_events") or []}
            for t in exp.get("session_must_include_types") or []:
                if t not in sess_types:
                    exp = dict(exp)
                    exp.setdefault("_assembled_failures", []).append(
                        f"session_events missing type {t!r}"
                    )
        else:
            raw = case.get("mock_executor_output") or ""
            source = case.get("search_results") or ""
            text = apply_fact_filters(raw, source, case.get("input", ""))
    finally:
        if fake_today:
            if prev_fake is None:
                os.environ.pop("KAIRI_FAKE_TODAY", None)
            else:
                os.environ["KAIRI_FAKE_TODAY"] = prev_fake
    failures = check_expectations(text, exp, carryover_ok=carryover_ok)
    failures.extend(exp.get("_assembled_failures") or [])
    return (len(failures) == 0, text, failures)


@contextmanager
def pinned_locale(locale: str = "ja"):
    """免責文の言語は settings.locale 依存。ローカル設定に結果が左右されないよう固定する。"""
    from app.core.runtime_state import temporary_settings

    with temporary_settings(locale=locale):
        yield


def main() -> int:
    cases = load_cases()
    if not cases:
        print("No cases found in", CASES_DIR)
        return 2
    passed = 0
    failed = 0
    print(f"Running {len(cases)} eval cases...\n")
    with pinned_locale("ja"):
        for case in cases:
            ok, text, failures = run_case(case)
            cid = case.get("id", case.get("_path"))
            if ok:
                passed += 1
                print(f"PASS  {cid}")
            else:
                failed += 1
                print(f"FAIL  {cid}")
                for f in failures:
                    print(f"      - {f}")
                preview = (text or "")[:120].replace("\n", "\\n")
                print(f"      output_preview: {preview!r}")
    print(f"\n{passed} passed, {failed} failed / {len(cases)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
