#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from datetime import datetime

def norm_one(src_path: Path, dst_path: Path):
    obj = json.loads(src_path.read_text(encoding="utf-8"))

    # 1) 入力が {"symbol": "...", "historical":[...]} のケース（例: AAPL.json） :contentReference[oaicite:5]{index=5}
    if isinstance(obj, dict) and "historical" in obj and isinstance(obj["historical"], list):
        rows = obj["historical"]

    # 2) すでに list[dict] のケース（backtestキャッシュ想定）
    elif isinstance(obj, list):
        rows = obj

    else:
        raise ValueError(f"Unknown JSON schema: {src_path}")

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = r.get("date")
        if not d:
            continue

        # 必須キーを揃える
        out.append({
            "date":   d,
            "open":   float(r.get("open", 0) or 0),
            "high":   float(r.get("high", 0) or 0),
            "low":    float(r.get("low", 0) or 0),
            "close":  float(r.get("close", 0) or 0),
            "volume": float(r.get("volume", 0) or 0),
        })

    # 日付昇順に統一（重要）
    def keyfn(x):
        return datetime.strptime(x["date"], "%Y-%m-%d")
    out.sort(key=keyfn)

    dst_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

def main():
    # ★ここだけ変えてください
    INPUT_DIR = Path(r"D:\personal\backend\local_historical_data")      # 600本JSONがあるフォルダ
    CACHE_DIR = Path(r"D:\personal\backend\.backtest_cache")  # backtest.py の CACHE_DIR と合わせる :contentReference[oaicite:6]{index=6}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    n = 0
    for src in INPUT_DIR.glob("*.json"):
        ticker = src.stem.upper()
        dst = CACHE_DIR / f"{ticker}.json"
        try:
            norm_one(src, dst)
            n += 1
        except Exception as e:
            print(f"SKIP {src.name}: {e}")

    print(f"OK: cached {n} tickers -> {CACHE_DIR}")

if __name__ == "__main__":
    main()