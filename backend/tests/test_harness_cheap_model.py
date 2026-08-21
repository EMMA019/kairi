"""Cheap-model harness: verify loop, citation-first, grounding retry."""
from __future__ import annotations

from app.core.auto_execution_loop.helpers import ensure_executor_guards
from app.core.harness.citation_first import build_citation_first_block, extract_grounded_quotes
from app.core.harness.grounding_retry import (
    candidate_score,
    needs_grounding_retry,
    pick_better_grounded,
    should_sample_hard,
)
from app.core.harness.verify_loop import (
    record_test_outcome,
    should_force_verify,
    verify_reinject_message,
    wrote_code_file,
)
from app.core.search.formatter import format_for_prompt


def test_wrote_code_file_detects_source_not_markdown():
    assert wrote_code_file('<file path="app/main.py">print(1)</file>')
    assert wrote_code_file('<edit path="src/App.tsx" instruction="x">y</edit>')
    assert not wrote_code_file('<file path="README.md">hello</file>')
    assert not wrote_code_file("just chatting")


def test_record_test_outcome_pytest_pass_and_fail():
    fail = record_test_outcome(
        "<run_command>pytest tests/test_foo.py -q</run_command>",
        ["===== 1 failed, 2 passed in 0.1s ====="],
    )
    assert fail["ran"] is True
    assert fail["passed"] is False

    ok = record_test_outcome(
        "<run_command>pytest -q</run_command>",
        ["===== 3 passed in 0.1s ====="],
    )
    assert ok["ran"] is True
    assert ok["passed"] is True


def test_should_force_verify_only_for_code_tasks():
    assert should_force_verify(
        mode="task", wrote_code=True, tests_passed=False, attempts=0
    )
    assert not should_force_verify(
        mode="chat", wrote_code=True, tests_passed=False, attempts=0
    )
    assert not should_force_verify(
        mode="coding", wrote_code=True, tests_passed=True, attempts=0
    )
    assert not should_force_verify(
        mode="task", wrote_code=True, tests_passed=False, attempts=2
    )
    msg = verify_reinject_message(attempt=1)
    assert "<run_command>" in msg
    assert "pytest" in msg


def test_citation_first_extracts_numbered_quotes():
    src = format_for_prompt(
        [
            {
                "title": "SanDisk announces 100% excess cash return",
                "snippet": "The board approved returning 100% of excess cash to shareholders.",
                "url": "https://example.com/sndk",
                "source": "brave",
            }
        ],
        query="SNDK",
        include_contract=False,
    )
    quotes = extract_grounded_quotes(src)
    assert quotes
    assert quotes[0].startswith("- [1]")
    assert "100%" in quotes[0] or "excess cash" in quotes[0]
    block = build_citation_first_block(src)
    assert "引用ファースト" in block
    assert "[1]" in block


def test_citation_first_empty_on_no_results_placeholder():
    assert extract_grounded_quotes("") == []
    assert build_citation_first_block("クエリに十分関連する情報は見つかりませんでした。") == ""


def test_executor_guard_adds_citation_first_when_search():
    with_search = ensure_executor_guards("base", has_search=True)
    assert "引用ファースト" in with_search
    no_search = ensure_executor_guards("base", has_search=False)
    assert "ソースなしターン" in no_search
    assert "引用ファースト" not in no_search


def test_grounding_retry_triggers_on_heavy_strip():
    before = "A" * 200 + " extra invented paragraph about ゼブラトン騎手 winning."
    after = "A" * 100
    assert needs_grounding_retry(before, after)
    assert not needs_grounding_retry("short ok", "short ok")


def test_pick_better_prefers_less_rewritten_alt():
    first_raw = "invented " * 40
    first_g = "tiny"
    alt_raw = "grounded answer from [1] only"
    alt_g = "grounded answer from [1] only"
    assert pick_better_grounded(first_raw, first_g, alt_raw, alt_g) == alt_g
    assert candidate_score(alt_raw, alt_g) > candidate_score(first_raw, first_g)


def test_hard_sample_heuristic():
    assert should_sample_hard("今日の米国株どうだった？", mode="chat", has_search=True)
    assert not should_sample_hard("hi", mode="chat", has_search=False)
    assert not should_sample_hard("pytest を直して", mode="task", has_search=False)
