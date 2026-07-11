#!/usr/bin/env python3
"""
scripts/generate_trend_data.py
==============================
strategies_history/ 以下の全 {date}.json を読み込み、
TrendPage 用の trend_data.json を生成する。

出力: frontend/public/content/strategies_history/trend_data.json

実行:
    python scripts/generate_trend_data.py

タスクスケジューラ: generate_strategies.py の直後に実行推奨
"""
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR  = Path(r"D:\program\personal\frontend\public\content") / "strategies_history"
OUTPUT_FILE  = HISTORY_DIR / "trend_data.json"


def main():
    print("=" * 50)
    print("  TREND DATA GENERATOR")
    print("=" * 50)

    # ── 1. 全JSONファイルを日付順に読み込む ──────────
    json_files = sorted([
        f for f in HISTORY_DIR.glob("*.json")
        if f.stem not in ("trend_data", "dates")  # 自分自身は除外
    ])

    if not json_files:
        print("❌ strategies_history/ にJSONファイルが見つかりません")
        return

    print(f"\n📂 {len(json_files)} ファイルを検出")

    all_data = {}   # { "2026-02-19": { "NVDA": {ticker, scores, status}, ... } }
    dates    = []

    for f in json_files:
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
            date  = f.stem  # ファイル名 = 日付
            all_data[date] = {item["ticker"]: item for item in items}
            dates.append(date)
            print(f"  ✅ {date}: {len(items)} 銘柄")
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")

    if len(dates) < 2:
        print("❌ 2日分以上のデータが必要です")
        return

    # ── 2. 全銘柄のヒストリーをまとめる ──────────────
    all_tickers = set()
    for d in all_data.values():
        all_tickers.update(d.keys())

    print(f"\n📊 集計: {len(dates)} 日 × {len(all_tickers)} 銘柄")

    ticker_history = {}  # { "NVDA": [ {date, scores, status}, ... ] }

    for ticker in sorted(all_tickers):
        history = []
        for date in dates:
            item = all_data[date].get(ticker)
            if not item:
                continue
            s = item["scores"]
            history.append({
                "date":      date,
                "composite": round(s.get("composite", 0), 1),
                "rs":        s.get("rs", 0),
                "ecr":       s.get("ecr_rank", 0),
                "vcp":       s.get("vcp", 0),
                "ses":       s.get("ses", 0),
                "canslim":   s.get("canslim", 0),
                "status":    item.get("status", "WAIT"),
            })

        if len(history) >= 2:
            ticker_history[ticker] = history

    # ── 3. 出力JSON生成 ───────────────────────────────
    output = {
        "generated_at": datetime.now().isoformat(),
        "dates":        dates,          # TrendPage が参照する日付一覧
        "tickers":      ticker_history, # 全銘柄のヒストリー
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\n✅ 出力完了: {OUTPUT_FILE}")
    print(f"   日付範囲: {dates[0]} → {dates[-1]} ({len(dates)} 日)")
    print(f"   銘柄数:   {len(ticker_history)}")
    print(f"   ファイルサイズ: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
