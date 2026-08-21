# Kairi Eval Harness

正規表現パッチやプロンプト変更の回帰を防ぐオフライン評価です。

## 実行

```bash
cd backend
python evals/run_evals.py
```

LLM は呼ばず、`mock_executor_output` に fact filter / citation / carryover を通して期待性質を判定します。

## ケース追加

`evals/cases/*.yaml` に事故パターンを追加してください。最低限のフィールド:

- `id` / `description`
- `input` / `history` / `search_results`
- `mock_executor_output`（または `carryover_fixture`）
- `expectations`（`must_not_contain` / `ends_with_terminal` / `golden_output` 等）
- `pipeline`: `fact_filters_only` | `carryover_only`

### 違和感ログから雛形を作る

```bash
python evals/from_violations.py              # プレビュー
python evals/from_violations.py --write      # evals/drafts/ に保存
```

ドラフトの expectations を埋めたら `evals/cases/` へ移すか `--promote` を使います。

### ゴールデン出力スナップショット

```bash
python evals/run_golden.py --record   # 現状フィルタ出力を記録
python evals/run_golden.py --check    # 差分検知
KAIRI_LIVE_EVALS=1 python evals/run_golden.py --live  # LLM 煙テスト（任意）
```

`evals/quality_ab.json` is a 30-task **human** A/B seed (not scored by this harness). See [docs/QUALITY.md](../../docs/QUALITY.md).
