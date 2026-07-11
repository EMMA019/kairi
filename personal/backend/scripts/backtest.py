#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest.py — RS Rising Swing Backtest (COKE-style)
===================================================
目的:
  ご主人様の裁量に近い「RS上昇スイング（COKE型）」を、日足OHLC + daily score(history)で再現する。

戦略（ver.1 固定）
-----------------
Signal day = t (strategies_historyの1日分ファイルのdate)

エントリー条件（t時点）:
  1) RS[t-2] < RS[t-1] < RS[t]（3日連続上昇）
  2) RS[t] >= 70
  3) ECR[t] >= 50
  4) COMPOSITE[t] >= 50
  5) Close[t] >= 0.95 * (過去20営業日のHigh最大)  ※高値圏
  6) Volume[t] >= 過去20営業日の平均出来高

エントリー:
  - 翌営業日(t+1)のOpenで買い

損切り:
  A) エントリー日の安値(entry_low)を割ったら損切り（翌日以降）
  B) 直近5営業日のスイング安値(swing_low)を割ったら損切り（翌日以降）
  ※ATRストップは使わない

利確/手仕舞い:
  1) RSが2日連続低下（RS[d] < RS[d-1] < RS[d-2]）でクローズ成行（Close）
  2) 10日高値からの反落：entry後の直近10日High最大(high10)から
     Close <= high10 * (1 - pullback_pct) でクローズ
     既定 pullback_pct=0.02 (2%反落)
  3) 最大保有 max_hold_days（既定20日）でクローズ

注意:
  - RSは「strategies_historyに保存されたスコア」を時系列で参照します
    （株価からRSを再計算するのではなく、あなたのRSスコアを使う）
  - RS欠損日がある場合、RS利確条件はスキップされます

入出力:
  - input: frontend/public/content/strategies_history/*.json
  - output: frontend/public/content/backtest_results.json
  - OHLC: .backtest_cache優先、無ければ --local-ohlc-dir から {TICKER}.json
  - FMP fetch: --no-fetch で無効
"""

import os, sys, json, time, argparse, glob, math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests

# ── パス ────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent  # .../backend
HISTORY_DIR  = ROOT_DIR / "frontend" / "public" / "content" / "strategies_history"
OUTPUT_DIR   = ROOT_DIR / "frontend" / "public" / "content"
OUTPUT_FILE  = OUTPUT_DIR / "backtest_results.json"
CACHE_DIR    = ROOT_DIR / ".backtest_cache"
CACHE_DIR.mkdir(exist_ok=True)

FMP_KEY  = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

# ── CLI ────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()

    # data
    p.add_argument("--no-fetch", action="store_true", help="FMP fetchしない（キャッシュ/ローカルのみ）")
    p.add_argument("--local-ohlc-dir", default="", help="ティッカー別OHLC JSONフォルダ（cache欠損時に使用）")
    p.add_argument("--cache-ttl-days", type=int, default=7, help="OHLCキャッシュTTL（日）")

    # signal selection
    p.add_argument("--status-filter", default="ACTION", help="ACTION/WAIT/ALL")
    p.add_argument("--max-signals", type=int, default=999999, help="処理上限（デバッグ用）")

    # strategy thresholds (fixed per your request)
    p.add_argument("--rs-threshold", type=float, default=70.0)
    p.add_argument("--ecr-threshold", type=float, default=50.0)
    p.add_argument("--composite-threshold", type=float, default=50.0)

    # condition lookbacks
    p.add_argument("--rs-rise-days", type=int, default=3, help="RS連続上昇日数（既定3）")
    p.add_argument("--high-lookback", type=int, default=20, help="高値圏判定のlookback（日）")
    p.add_argument("--high-near", type=float, default=0.95, help="高値圏閾値（0.95=20日高値の95%）")
    p.add_argument("--vol-lookback", type=int, default=20, help="出来高平均lookback")
    p.add_argument("--vol-mult", type=float, default=1.0, help="当日出来高 >= avg * mult")

    # exits
    p.add_argument("--swing-low-lookback", type=int, default=5, help="スイング安値lookback（日）")
    p.add_argument("--max-hold-days", type=int, default=20, help="最大保有（日）")
    p.add_argument("--pullback-lookback", type=int, default=10, help="反落判定の高値lookback（日）")
    p.add_argument("--pullback-pct", type=float, default=0.02, help="10日高値からの反落率（0.02=2%）")

    # execution costs (optional)
    p.add_argument("--slippage-bps", type=float, default=0.0, help="スリッページ(bps)")
    p.add_argument("--commission-per-side", type=float, default=0.0, help="片道固定手数料（entry/exitそれぞれ）")

    return p.parse_args()

# ── OHLC normalize ───────────────────────────────────────
def _get_any(d: dict, keys, default=None):
    for k in keys:
        if k in d:
            return d.get(k)
        kl = k.lower()
        for dk in d.keys():
            if isinstance(dk, str) and dk.lower() == kl:
                return d.get(dk)
    return default

def normalize_rows(obj, src_name: str):
    if isinstance(obj, dict) and isinstance(obj.get("historical"), list):
        rows = obj["historical"]
    elif isinstance(obj, list):
        rows = obj
    else:
        raise ValueError(f"unknown OHLC schema: {src_name}")

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _get_any(r, ("date",))
        if not d:
            continue
        try:
            out.append({
                "date":   str(d)[:10],
                "open":   float(_get_any(r, ("open","Open"))   or 0),
                "high":   float(_get_any(r, ("high","High"))   or 0),
                "low":    float(_get_any(r, ("low","Low"))     or 0),
                "close":  float(_get_any(r, ("close","Close")) or 0),
                "volume": float(_get_any(r, ("volume","Volume")) or 0),
            })
        except Exception:
            continue

    out.sort(key=lambda x: x["date"])
    dedup = {}
    for r in out:
        dedup[r["date"]] = r
    return [dedup[k] for k in sorted(dedup.keys())]

def build_date_index(bars):
    return {b["date"]: i for i, b in enumerate(bars)}

def bps_to_mult(bps: float) -> float:
    return 1.0 + (bps / 10000.0)

def apply_slippage(price: float, side: str, slippage_bps: float) -> float:
    if price <= 0 or slippage_bps <= 0:
        return price
    mult = bps_to_mult(slippage_bps)
    if side == "buy":
        return price * mult
    if side == "sell":
        return price / mult
    return price

def load_local_ohlc_from_dir(ticker: str, local_dir: Path):
    src = local_dir / f"{ticker}.json"
    if not src.exists():
        src2 = local_dir / f"{ticker.lower()}.json"
        if src2.exists():
            src = src2
        else:
            return []
    try:
        obj = json.loads(src.read_text(encoding="utf-8"))
        return normalize_rows(obj, src.name)
    except Exception as e:
        print(f"  ⚠️ local ohlc load failed ({ticker}): {e}")
        return []

def fetch_ohlc(ticker: str, no_fetch: bool, cache_ttl_days: int, local_ohlc_dir: str):
    ticker = ticker.upper()
    cache_path = CACHE_DIR / f"{ticker}.json"

    # cache
    if cache_path.exists():
        try:
            if no_fetch:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                return normalize_rows(cached, cache_path.name)
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if (datetime.now() - mtime).days < cache_ttl_days:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                return normalize_rows(cached, cache_path.name)
        except Exception as e:
            print(f"  ⚠️ cache read failed ({ticker}): {e}")

    # local
    if local_ohlc_dir:
        local_dir = Path(local_ohlc_dir).expanduser().resolve()
        if local_dir.exists():
            rows = load_local_ohlc_from_dir(ticker, local_dir)
            if rows:
                try:
                    cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
                return rows

    # no fetch
    if no_fetch:
        return []

    # fetch FMP
    if not FMP_KEY:
        print("  ⚠️ FMP_API_KEY未設定（no-fetchでもlocal/cacheも無し）")
        return []
    try:
        url = f"{FMP_BASE}/historical-price-eod/full?symbol={ticker}&apikey={FMP_KEY}"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        bars = data.get("historical", data if isinstance(data, list) else [])
        bars = normalize_rows(bars, f"FMP:{ticker}")
        if bars:
            cache_path.write_text(json.dumps(bars, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)
        return bars
    except Exception as e:
        print(f"  ⚠️ OHLC fetch failed({ticker}): {e}")
        return []

# ── strategies_history load (scores time series) ──────────
def load_history_files(history_dir: Path):
    files = sorted(glob.glob(str(history_dir / "*.json")))
    if not files:
        return []
    return files

def parse_history_file(path: str):
    date_str = Path(path).stem[:10]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return date_str, []

    items = data if isinstance(data, list) else data.get("all_data", [])
    out = []
    for it in items:
        if not isinstance(it, dict) or "ticker" not in it:
            continue
        scores = it.get("scores", {}) or {}
        out.append({
            "date": date_str,
            "ticker": str(it["ticker"]).upper(),
            "status": it.get("status", ""),
            "vcp": float(scores.get("vcp", 0) or 0),
            "rs": float(scores.get("rs", 0) or 0),
            "ecr": float(scores.get("ecr_rank", 0) or 0),
            "canslim": float(scores.get("canslim", 0) or 0),
            "ses": float(scores.get("ses", 0) or 0),
            "composite": float(scores.get("composite", 0) or 0),
            "sector": it.get("sector", "N/A"),
        })
    return date_str, out

def build_score_timeseries(history_files: list[str]):
    # per ticker: date -> scores
    by_ticker = defaultdict(dict)
    all_dates = []
    for fp in history_files:
        d, rows = parse_history_file(fp)
        all_dates.append(d)
        for r in rows:
            by_ticker[r["ticker"]][d] = r
    all_dates = sorted(set(all_dates))
    return by_ticker, all_dates

# ── helpers for conditions ────────────────────────────────
def avg_volume(bars, end_idx_exclusive: int, lookback: int) -> float:
    if lookback <= 0:
        return 0.0
    start = max(0, end_idx_exclusive - lookback)
    vols = [bars[i]["volume"] for i in range(start, end_idx_exclusive) if bars[i]["volume"] > 0]
    if not vols:
        return 0.0
    return sum(vols) / len(vols)

def max_high(bars, end_idx_inclusive: int, lookback: int) -> float:
    if lookback <= 0:
        return 0.0
    start = max(0, end_idx_inclusive - lookback + 1)
    hs = [bars[i]["high"] for i in range(start, end_idx_inclusive + 1)]
    return max(hs) if hs else 0.0

def min_low(bars, end_idx_inclusive: int, lookback: int) -> float:
    if lookback <= 0:
        return 0.0
    start = max(0, end_idx_inclusive - lookback + 1)
    ls = [bars[i]["low"] for i in range(start, end_idx_inclusive + 1)]
    return min(ls) if ls else 0.0

# ── strategy core ─────────────────────────────────────────
def rs_rising_3(score_by_date: dict, dates_sorted: list[str], t_date: str, rise_days: int) -> bool:
    # Need t- (rise_days-1) ... t
    if rise_days < 2:
        return True
    try:
        idx = dates_sorted.index(t_date)
    except ValueError:
        return False
    if idx < (rise_days - 1):
        return False

    # strictly increasing
    prev = None
    for k in range(idx - (rise_days - 1), idx + 1):
        d = dates_sorted[k]
        row = score_by_date.get(d)
        if not row:
            return False
        cur = float(row.get("rs", 0) or 0)
        if prev is not None and not (prev < cur):
            return False
        prev = cur
    return True

def rs_two_day_decline(score_by_date: dict, dates_sorted: list[str], d0: str) -> bool:
    # RS[d0] < RS[d-1] < RS[d-2]
    try:
        idx = dates_sorted.index(d0)
    except ValueError:
        return False
    if idx < 2:
        return False
    r0 = score_by_date.get(dates_sorted[idx])
    r1 = score_by_date.get(dates_sorted[idx-1])
    r2 = score_by_date.get(dates_sorted[idx-2])
    if not (r0 and r1 and r2):
        return False
    rs0 = float(r0.get("rs", 0) or 0)
    rs1 = float(r1.get("rs", 0) or 0)
    rs2 = float(r2.get("rs", 0) or 0)
    return (rs0 < rs1) and (rs1 < rs2)

def simulate_trade_rs_swing(
    ticker: str,
    t_date: str,
    signal_row: dict,
    ticker_scores_by_date: dict,
    all_dates_sorted: list[str],
    bars: list[dict],
    args
):
    date_to_idx = build_date_index(bars)
    if t_date not in date_to_idx:
        return None
    t_i = date_to_idx[t_date]

    # Ensure enough OHLC history for high/vol lookbacks
    if t_i < max(args.high_lookback, args.vol_lookback, args.swing_low_lookback) + 2:
        return None

    # --- Entry filters on scores ---
    if not rs_rising_3(ticker_scores_by_date, all_dates_sorted, t_date, args.rs_rise_days):
        return None

    rs_t = float(signal_row.get("rs", 0) or 0)
    ecr_t = float(signal_row.get("ecr", 0) or 0)
    comp_t = float(signal_row.get("composite", 0) or 0)

    if rs_t < args.rs_threshold:
        return None
    if ecr_t < args.ecr_threshold:
        return None
    if comp_t < args.composite_threshold:
        return None

    # --- Price location: near highs ---
    highN = max_high(bars, t_i, args.high_lookback)
    if highN <= 0:
        return None
    if bars[t_i]["close"] < highN * args.high_near:
        return None

    # --- Volume filter ---
    av = avg_volume(bars, t_i, args.vol_lookback)
    if av <= 0:
        return None
    if bars[t_i]["volume"] < av * args.vol_mult:
        return None

    # --- Entry next day open ---
    entry_i = t_i + 1
    if entry_i >= len(bars):
        return None

    entry_price = apply_slippage(bars[entry_i]["open"], "buy", args.slippage_bps)
    if entry_price <= 0:
        return None

    entry_date = bars[entry_i]["date"]
    entry_low  = bars[entry_i]["low"]  # initial low for stop rule A

    # swing low based on last swing_low_lookback days BEFORE entry
    swing_low = min_low(bars, entry_i - 1, args.swing_low_lookback)
    if swing_low <= 0:
        swing_low = entry_low

    commission = float(args.commission_per_side or 0.0)

    # --- Walk forward ---
    exit_i = None
    exit_price = None
    outcome = "timeout"

    # track rolling high for pullback exit
    highest_recent = bars[entry_i]["high"]
    highs_window = []  # keep last pullback_lookback highs
    highs_window.append(bars[entry_i]["high"])

    last_i = min(entry_i + args.max_hold_days, len(bars) - 1)

    # start checking from entry_i+1 (because "initial low break" after entry day)
    for i in range(entry_i + 1, last_i + 1):
        b = bars[i]

        # update rolling high window
        highs_window.append(b["high"])
        if len(highs_window) > args.pullback_lookback:
            highs_window.pop(0)
        highest_recent = max(highs_window) if highs_window else highest_recent

        # Stop A: break entry_day_low
        if b["low"] < entry_low:
            exit_i = i
            exit_price = apply_slippage(entry_low, "sell", args.slippage_bps)
            outcome = "stop_entry_low"
            break

        # Stop B: break swing low
        if b["low"] < swing_low:
            exit_i = i
            exit_price = apply_slippage(swing_low, "sell", args.slippage_bps)
            outcome = "stop_swing_low"
            break

        # Take profit 1: RS two-day decline (use scores for that date)
        d = b["date"]
        if rs_two_day_decline(ticker_scores_by_date, all_dates_sorted, d):
            exit_i = i
            exit_price = apply_slippage(b["close"], "sell", args.slippage_bps)
            outcome = "tp_rs_decline"
            break

        # Take profit 2: pullback from recent high10
        if highest_recent > 0:
            if b["close"] <= highest_recent * (1.0 - args.pullback_pct):
                exit_i = i
                exit_price = apply_slippage(b["close"], "sell", args.slippage_bps)
                outcome = "tp_pullback"
                break

    if exit_i is None:
        exit_i = last_i
        exit_price = apply_slippage(bars[exit_i]["close"], "sell", args.slippage_bps)
        outcome = "timeout"

    # costs (simple)
    gross_pnl = (exit_price / entry_price - 1.0) * 100.0
    net_pnl = gross_pnl
    if commission > 0:
        net_pnl -= (commission / entry_price) * 100.0
        net_pnl -= (commission / exit_price) * 100.0

    # R-like metric: use risk = entry_price - min(entry_low, swing_low)
    risk_level = min(entry_low, swing_low)
    risk = max(entry_price - risk_level, 1e-9)
    r_value = (exit_price - entry_price) / risk

    return {
        "ticker": ticker,
        "signal_date": t_date,
        "entry_date": entry_date,
        "exit_date": bars[exit_i]["date"],

        "entry_price": round(entry_price, 2),
        "exit_price": round(exit_price, 2),

        "entry_low": round(entry_low, 2),
        "swing_low": round(swing_low, 2),

        "outcome": outcome,
        "hold_days": int(exit_i - entry_i),

        "pnl_pct_gross": round(gross_pnl, 2),
        "pnl_pct": round(net_pnl, 2),
        "r_value": round(r_value, 2),

        # snapshot scores at signal
        "vcp": float(signal_row.get("vcp", 0) or 0),
        "rs": rs_t,
        "ecr": ecr_t,
        "canslim": float(signal_row.get("canslim", 0) or 0),
        "ses": float(signal_row.get("ses", 0) or 0),
        "composite": comp_t,
        "sector": signal_row.get("sector", "N/A"),
    }

# ── stats ────────────────────────────────────────────────
def stats(trades):
    if not trades:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "pf": 0.0, "avg_pnl_pct": 0.0, "avg_hold": 0.0}

    n = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]

    # profit factor on R
    profit = sum(t["r_value"] for t in wins)
    loss = abs(sum(t["r_value"] for t in losses)) or 1e-9

    return {
        "n": n,
        "win_rate": round(len(wins) / n * 100.0, 1),
        "avg_r": round(sum(t["r_value"] for t in trades) / n, 2),
        "pf": round(profit / loss, 2),
        "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / n, 2),
        "avg_hold": round(sum(t["hold_days"] for t in trades) / n, 1),
        "best_r": round(max(t["r_value"] for t in trades), 2),
        "worst_r": round(min(t["r_value"] for t in trades), 2),
        "by_outcome": dict(sorted(
            {k: len([t for t in trades if t["outcome"] == k]) for k in set(t["outcome"] for t in trades)}.items(),
            key=lambda x: -x[1]
        )),
    }

# ── main ────────────────────────────────────────────────
def main():
    args = parse_args()

    print("====== RS RISING SWING BACKTEST (COKE-style) ======")
    print(f"  RS rising days: {args.rs_rise_days} | RS>={args.rs_threshold} | ECR>={args.ecr_threshold} | COM>={args.composite_threshold}")
    print(f"  Near-high: lookback={args.high_lookback}, near={args.high_near}")
    print(f"  Volume: lookback={args.vol_lookback}, mult={args.vol_mult}")
    print(f"  Exits: swing_low_lb={args.swing_low_lookback}, pullback_lb={args.pullback_lookback}, pullback_pct={args.pullback_pct}, max_hold={args.max_hold_days}")
    print(f"  Costs: slippage={args.slippage_bps}bps, commission/side={args.commission_per_side}")

    history_files = load_history_files(HISTORY_DIR)
    if not history_files:
        print(f"❌ strategies_history not found: {HISTORY_DIR}")
        sys.exit(1)

    scores_by_ticker, all_dates_sorted = build_score_timeseries(history_files)

    # Build candidate signals = rows on each date satisfying status filter and thresholds (except RS rising needs prev days)
    signals = []
    for d in all_dates_sorted:
        # each ticker row on that date
        for ticker, m in scores_by_ticker.items():
            row = m.get(d)
            if not row:
                continue
            status = row.get("status", "")
            if args.status_filter != "ALL" and status != args.status_filter:
                continue
            # basic thresholds (RS rising checked later)
            if float(row.get("rs", 0) or 0) < args.rs_threshold:
                continue
            if float(row.get("ecr", 0) or 0) < args.ecr_threshold:
                continue
            if float(row.get("composite", 0) or 0) < args.composite_threshold:
                continue
            signals.append((ticker, d, row))

    signals = signals[:args.max_signals]
    print(f"✅ Candidate signals: {len(signals)}")

    # OHLC cache per ticker
    ohlc_cache = {}
    trades = []
    miss_ohlc = 0

    print("\n--- Simulating ---")
    for i, (ticker, d, row) in enumerate(signals, 1):
        if ticker not in ohlc_cache:
            bars = fetch_ohlc(ticker, args.no_fetch, args.cache_ttl_days, args.local_ohlc_dir)
            ohlc_cache[ticker] = bars
            if i % 50 == 0 or i == 1:
                print(f"  [{i}/{len(signals)}] {ticker}: {len(bars)} bars")
        bars = ohlc_cache.get(ticker) or []
        if not bars:
            miss_ohlc += 1
            continue

        tr = simulate_trade_rs_swing(
            ticker=ticker,
            t_date=d,
            signal_row=row,
            ticker_scores_by_date=scores_by_ticker[ticker],
            all_dates_sorted=all_dates_sorted,
            bars=bars,
            args=args
        )
        if tr:
            trades.append(tr)

    print(f"\n✅ Trades: {len(trades)} (OHLC missing: {miss_ohlc})")

    overall = stats(trades)
    print("\n--- Summary ---")
    print(f"n={overall['n']}, win_rate={overall['win_rate']}%, avgR={overall['avg_r']:+.2f}, PF={overall['pf']:.2f}, avgPnL%={overall['avg_pnl_pct']:+.2f}, avgHold={overall['avg_hold']}d")
    print(f"outcomes={overall['by_outcome']}")

    output = {
        "generated_at": datetime.now().isoformat(),
        "strategy": "rs_rising_swing_v1",
        "params": {
            "status_filter": args.status_filter,
            "max_signals": args.max_signals,

            "rs_rise_days": args.rs_rise_days,
            "rs_threshold": args.rs_threshold,
            "ecr_threshold": args.ecr_threshold,
            "composite_threshold": args.composite_threshold,

            "high_lookback": args.high_lookback,
            "high_near": args.high_near,
            "vol_lookback": args.vol_lookback,
            "vol_mult": args.vol_mult,

            "swing_low_lookback": args.swing_low_lookback,
            "pullback_lookback": args.pullback_lookback,
            "pullback_pct": args.pullback_pct,
            "max_hold_days": args.max_hold_days,

            "slippage_bps": args.slippage_bps,
            "commission_per_side": args.commission_per_side,

            "no_fetch": args.no_fetch,
            "cache_ttl_days": args.cache_ttl_days,
            "local_ohlc_dir": args.local_ohlc_dir,
        },
        "overall": overall,
        "trades": trades,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Saved: {OUTPUT_FILE}")
    print(f"   size: {OUTPUT_FILE.stat().st_size/1024:.1f} KB")
    print("====== DONE ======")

if __name__ == "__main__":
    main()