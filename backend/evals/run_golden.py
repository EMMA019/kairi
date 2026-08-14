"""ゴールデン出力スナップショット / 任意のライブ煙テスト。

使い方:
  # 既存 cases のフィルタ出力を golden/ に記録
  python evals/run_golden.py --record

  # 記録済み golden と現状出力を比較（CI でも可）
  python evals/run_golden.py --check

  # 本物パイプライン + 偽物モデル（keyless assembled snapshot）
  python evals/run_golden.py --live
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
CASES_DIR = Path(__file__).resolve().parent / "cases"


def _case_key(case: dict) -> str:
    cid = case.get("id") or "unknown"
    raw = case.get("mock_executor_output") or ""
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{cid}__{digest}"


def record_goldens() -> int:
    from evals.run_evals import apply_fact_filters, load_cases
    from app.core.runtime_state import temporary_settings

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with temporary_settings(locale="ja"):
        for case in load_cases():
            if case.get("pipeline", "fact_filters_only") != "fact_filters_only":
                continue
            raw = case.get("mock_executor_output") or ""
            if not raw.strip():
                continue
            out = apply_fact_filters(
                raw, case.get("search_results") or "", case.get("input") or ""
            )
            key = _case_key(case)
            path = GOLDEN_DIR / f"{key}.txt"
            path.write_text(out, encoding="utf-8")
            meta = {
                "id": case.get("id"),
                "key": key,
                "input": case.get("input"),
            }
            (GOLDEN_DIR / f"{key}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"recorded {path.name}")
            n += 1
    print(f"{n} golden file(s) written to {GOLDEN_DIR}")
    return 0


def check_goldens() -> int:
    from evals.run_evals import apply_fact_filters, load_cases
    from app.core.runtime_state import temporary_settings

    if not GOLDEN_DIR.exists():
        print("No golden/ directory. Run with --record first.")
        return 2

    failed = 0
    checked = 0
    with temporary_settings(locale="ja"):
        for case in load_cases():
            if case.get("pipeline", "fact_filters_only") != "fact_filters_only":
                continue
            raw = case.get("mock_executor_output") or ""
            if not raw.strip():
                continue
            key = _case_key(case)
            path = GOLDEN_DIR / f"{key}.txt"
            if not path.exists():
                continue
            expected = path.read_text(encoding="utf-8")
            actual = apply_fact_filters(
                raw, case.get("search_results") or "", case.get("input") or ""
            )
            checked += 1
            if actual != expected:
                failed += 1
                print(f"FAIL  {case.get('id')} ({key})")
                print(f"      expected_len={len(expected)} actual_len={len(actual)}")
            else:
                print(f"PASS  {case.get('id')}")
    print(f"\n{checked - failed} passed, {failed} failed / {checked} checked")
    return 1 if failed else 0


def run_live_smoke() -> int:
    """Real pipeline + scripted mock LLM (keyless). Does not call a live LLM."""
    from evals.run_evals import load_cases, run_case, pinned_locale

    cases = [c for c in load_cases() if c.get("pipeline") == "assembled_loop"]
    if not cases:
        print("No assembled_loop cases found.")
        return 2
    passed = failed = 0
    print(f"Assembled-loop snapshots (real pipeline, fake model): {len(cases)}")
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
                preview = (text or "")[:120].replace("\n", " | ")
                print(f"      output_preview: {preview!r}")
    print(f"{passed} passed, {failed} failed / {len(cases)} total")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--record", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.record:
        return record_goldens()
    if args.check:
        return check_goldens()
    return run_live_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
