"""Force test-first verification after code writes (cheap-model coding harness)."""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_VERIFY_REINJECT = 2

UNVERIFIED_TEST_BANNER = (
    "\n\n*(ℹ️ Completion gate: automated tests were not run. "
    "Run pytest / npm test / go test before treating this as done.)*\n"
)

_CODE_FILE_TAG = re.compile(
    r"<(?:file|replace|edit)\b[^>]*\bpath\s*=\s*[\"'][^\"']+\.(py|js|ts|tsx|jsx|go|rs)[\"']",
    re.IGNORECASE,
)

_TEST_CMD = re.compile(
    r"(?:python\s+-m\s+)?(?:pytest|py_compile|unittest)\b"
    r"|npm\s+(?:test|run\s+test)\b"
    r"|npx\s+(?:vitest|jest)\b"
    r"|go\s+test\b"
    r"|cargo\s+test\b"
    r"|python\s+-m\s+compileall\b",
    re.IGNORECASE,
)


def wrote_code_file(stream_response: str) -> bool:
    """True when this turn saved/edited a source file (not markdown/json)."""
    return bool(_CODE_FILE_TAG.search(stream_response or ""))


def looks_like_test_command(text: str) -> bool:
    return bool(_TEST_CMD.search(text or ""))


def record_test_outcome(stream_response: str, tool_results: Optional[Iterable[str]]) -> dict[str, Any]:
    """Did this tool batch run tests, and did they pass?"""
    from app.core.auto_execution_loop.heuristics import _detect_success, _detect_test_failure

    ran = looks_like_test_command(stream_response or "")
    passed = False
    summaries: list[str] = []
    for raw in tool_results or []:
        blob = str(raw or "")
        if looks_like_test_command(blob):
            ran = True
        info = _detect_test_failure(blob)
        if info:
            ran = True
            summaries.append(str(info.get("summary") or ""))
            if info.get("success"):
                passed = True
        elif ran and _detect_success(blob) and looks_like_test_command(blob):
            passed = True
    return {"ran": ran, "passed": passed, "summary": "; ".join(s for s in summaries if s)}


def should_force_verify(
    *,
    mode: str,
    wrote_code: bool,
    tests_passed: bool,
    attempts: int,
    cap: int = MAX_VERIFY_REINJECT,
) -> bool:
    if mode not in ("task", "coding"):
        return False
    if not wrote_code or tests_passed:
        return False
    return attempts < cap


def verify_reinject_message(*, attempt: int, cap: int = MAX_VERIFY_REINJECT) -> str:
    return (
        "【検証ループ・未達】完了宣言は禁止。コードを書いたあとは必ず検証すること。\n"
        "1) テストが無ければ失敗するテストを先に <file> で tests/ に書く。\n"
        "2) <run_command> で pytest / npm test / go test / cargo test を実行する。\n"
        "3) 失敗ログを読んで修正し、再実行して通す。\n"
        "テストが通るまでユーザー向けの完了報告を出すな。"
        f"（検証リトライ {attempt}/{cap}）"
    )
