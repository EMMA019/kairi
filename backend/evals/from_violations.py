"""違和感ログ → eval ケース雛形。

使い方（backend/ から）:
  python evals/from_violations.py
  python evals/from_violations.py --date 2026-08-12
  python evals/from_violations.py --write

デフォルトは drafts/ に書き、本番 cases/ には --promote で移す。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

DRAFT_DIR = Path(__file__).resolve().parent / "drafts"
CASES_DIR = Path(__file__).resolve().parent / "cases"


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w一-龥ぁ-んァ-ヶー]+", "_", (text or "").strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return (s or "untitled")[:limit]


def _yaml_escape(s: str) -> str:
    return (s or "").replace("\r\n", "\n").rstrip() + "\n"


def render_case(entry: dict, index: int) -> tuple[str, str]:
    vtype = entry.get("violation_type") or "その他"
    user = entry.get("user_message") or ""
    ai = entry.get("ai_response") or ""
    reason = entry.get("reason") or ""
    source = entry.get("source") or "user"
    ts = entry.get("timestamp") or entry.get("_log_date") or ""
    case_id = f"draft_{_slug(vtype)}_{_slug(user, 24)}_{index:03d}"

    body = f"""id: {case_id}
description: >
  違和感ログ由来（{vtype} / source={source}）。
  reason: {reason or "（なし）"}
  logged_at: {ts}
  TODO: expectations を具体化し、不要ならこのファイルを削除。
input: |
{_indent(user, 2)}
history: []
search_results: |
  TODO: 当時の検索結果があれば貼る。無ければ空のまま。
mock_executor_output: |
{_indent(ai, 2)}
expectations:
  # まずは「悪化させない」ためのメモ。必要に応じて must_not_contain 等を足す。
  must_not_contain: []
  # golden_output を入れると出力スナップショット回帰になる（run_evals.py）
  # golden_output: |
  #   （望ましい整形後テキスト）
pipeline: fact_filters_only
meta:
  from_violation: true
  violation_type: {vtype}
  violation_source: {source}
"""
    return case_id, body


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    lines = _yaml_escape(text).splitlines() or [""]
    return "\n".join(pad + line if line else pad.rstrip() for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="違和感ログ → eval draft YAML")
    parser.add_argument("--date", help="YYYY-MM-DD（省略時は全日付）")
    parser.add_argument("--write", action="store_true", help="drafts/ に書き出す")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="drafts/ ではなく cases/ に直接書く（注意）",
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from app.core.violation_log import iter_all_violation_logs, list_violation_logs

    if args.date:
        _, logs = list_violation_logs(args.date)
    else:
        logs = iter_all_violation_logs()

    if not logs:
        print("No violation logs found.")
        return 0

    out_dir = CASES_DIR if args.promote else DRAFT_DIR
    if args.write or args.promote:
        out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for i, entry in enumerate(logs[: args.limit]):
        if not isinstance(entry, dict):
            continue
        case_id, body = render_case(entry, i)
        if args.write or args.promote:
            path = out_dir / f"{case_id}.yaml"
            path.write_text(body, encoding="utf-8")
            print(f"wrote {path.relative_to(BACKEND_ROOT)}")
            written += 1
        else:
            print("---")
            print(body)

    if not (args.write or args.promote):
        print(
            f"\n({len(logs[: args.limit])} cases previewed; "
            "re-run with --write to save under evals/drafts/)"
        )
    else:
        print(f"\n{written} draft case(s) written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
