#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_ohlc_to_backtest_cache.py (in-place version)

目的:
  D:\personal\backend\.backtest_cache にあるティッカー別JSONを、
  backtest.py が確実に読める形式へ「同じ場所で」正規化する。

対応入力:
  1) {"symbol": "...", "historical":[{date,open,high,low,close,volume,...}, ...]}
  2) [{date,open,high,low,close,volume,...}, ...]
  3) キーの大小混在 (Open/Close/Volume 等) も吸収

出力（上書き）:
  .backtest_cache/TICKER.json  （日付昇順の list[dict]）

使い方:
  # 既存ファイルを上書き（推奨）
  python import_ohlc_to_backtest_cache.py

  # 念のためバックアップも作る
  python import_ohlc_to_backtest_cache.py --backup

  # フォルダを明示したい場合
  python import_ohlc_to_backtest_cache.py --cache-dir D:\personal\backend\.backtest_cache
"""

import json
import os
from pathlib import Path
from datetime import datetime
import argparse
from typing import Any, Dict, List, Optional

REQUIRED = ("date", "open", "high", "low", "close", "volume")


def _parse_date(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def _get_any(d: Dict[str, Any], *keys: str, default=None):
    """大小キーゆれを吸収して値を取る"""
    for k in keys:
        if k in d:
            return d.get(k)
        kl = k.lower()
        if kl in d:
            return d.get(kl)
        ku = k.upper()
        if ku in d:
            return d.get(ku)
        kt = k.title()
        if kt in d:
            return d.get(kt)
    return default


def _to_float(x) -> float:
    if x is None:
        return 0.0
    try:
        return float(x)
    except Exception:
        return 0.0


def normalize_rows(obj: Any, src_name: str) -> List[Dict[str, Any]]:
    # schema 判定
    if isinstance(obj, dict) and isinstance(obj.get("historical"), list):
        rows = obj["historical"]
    elif isinstance(obj, list):
        rows = obj
    else:
        raise ValueError(f"unknown schema: {src_name}")

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue

        d = _get_any(r, "date")
        if not d or not isinstance(d, str):
            continue
        if _parse_date(d) is None:
            # date形式が違うなら捨てる（必要ならここで変換対応も可能）
            continue

        out.append({
            "date": d,
            "open":   _to_float(_get_any(r, "open")),
            "high":   _to_float(_get_any(r, "high")),
            "low":    _to_float(_get_any(r, "low")),
            "close":  _to_float(_get_any(r, "close")),
            "volume": _to_float(_get_any(r, "volume")),
        })

    # 日付昇順に統一（重要）
    out.sort(key=lambda x: x["date"])

    # 必須列チェック（念のため）
    if out:
        missing = [k for k in REQUIRED if k not in out[0]]
        if missing:
            raise ValueError(f"missing keys {missing}: {src_name}")

    return out


def process_file(path: Path, backup: bool, min_rows: int) -> str:
    """
    正規化して同じファイルへ上書き。
    戻り値: "ok" | "skip" | "fail"
    """
    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)

        rows = normalize_rows(obj, path.name)
        if len(rows) < min_rows:
            return "skip"

        # すでに正規化済みなら無駄な書き込みを避ける（mtime更新はしたいので書くかは好み）
        # ここでは「中身が同じでも必ずmtime更新」するため、書き込みは行う
        if backup:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                bak.write_text(raw, encoding="utf-8")

        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

        # --no-fetch の “7日以内” 判定に確実に通すためmtime更新
        os.utime(path, None)

        return "ok"

    except Exception:
        return "fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--cache-dir",
        default=r"D:\personal\backend\.backtest_cache",
        help="正規化対象の .backtest_cache フォルダ（デフォルトはD:\\personal\\backend\\.backtest_cache）"
    )
    ap.add_argument("--backup", action="store_true", help="元ファイルを .bak に退避（初回のみ）")
    ap.add_argument("--min-rows", type=int, default=60, help="短すぎるデータはskip（デフォルト60）")
    args = ap.parse_args()

    cache_dir = Path(args.cache_dir)
    if not cache_dir.exists():
        raise SystemExit(f"cache-dir not found: {cache_dir}")

    ok = skip = fail = 0
    for fp in cache_dir.glob("*.json"):
        res = process_file(fp, backup=args.backup, min_rows=args.min_rows)
        if res == "ok":
            ok += 1
        elif res == "skip":
            skip += 1
        else:
            fail += 1
            print(f"FAIL: {fp.name}")

    print(f"DONE: ok={ok}, skip={skip}, fail={fail}")
    print(f"cache_dir: {cache_dir}")


if __name__ == "__main__":
    main()