#!/usr/bin/env python3
"""
scripts/weekly_check.py — 週次スコア vs 株価パフォーマンス検証 v2
=============================================================
MFE/MAE/ATRストップ到達判定を追加。終値だけでなく
高値・安値ベースで実態に近いパフォーマンスを検証する。

使い方:
  python scripts/weekly_check.py --date 2026-02-19
  python scripts/weekly_check.py --date 2026-02-19 --no-fetch

出力:
  frontend/public/content/weekly_check.json
"""
import sys, json, os, time, argparse, glob
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import requests

# ── パス設定 ─────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent
OUTPUT_DIR  = ROOT_DIR / "frontend" / "public" / "content"
CACHE_DIR   = ROOT_DIR / ".backtest_cache"
OUTPUT_FILE = OUTPUT_DIR / "weekly_check.json"
CACHE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FMP_KEY  = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"
ATR_STOP_MULT = 2.0  # ストップ = エントリー - ATR × 2.0

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    p.add_argument('--no-fetch', action='store_true')
    return p.parse_args()

# ── OHLC取得（キャッシュ1日） ────────────────────────────
def fetch_ohlc(ticker: str, no_fetch: bool = False) -> list[dict]:
    cache_path = CACHE_DIR / f"{ticker}.json"
    if cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if (datetime.now() - mtime).total_seconds() < 86400:
            with open(cache_path, encoding='utf-8') as f:
                return json.load(f)
    if no_fetch:
        return []
    if not FMP_KEY:
        print("❌ FMP_API_KEY が未設定です")
        sys.exit(1)
    try:
        url  = f"{FMP_BASE}/historical-price-eod/full?symbol={ticker}&apikey={FMP_KEY}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # FMPはlistを直接返す場合とdictの場合がある
        if isinstance(data, list):
            raw_bars = data
        elif isinstance(data, dict):
            raw_bars = data.get('historical', [])
        else:
            raw_bars = []

        bars = sorted([{
            'date':  b['date'],
            'open':  float(b.get('open',  0) or 0),
            'high':  float(b.get('high',  0) or 0),
            'low':   float(b.get('low',   0) or 0),
            'close': float(b.get('close', 0) or 0),
        } for b in raw_bars if b.get('date')], key=lambda x: x['date'])

        cache_path.write_text(json.dumps(bars), encoding='utf-8')
        time.sleep(0.22)
        return bars
    except Exception as e:
        print(f"  ⚠ {ticker}: {e}")
        return []

# ── ヘルパー ─────────────────────────────────────────────
def get_entry(bars: list[dict], signal_date: str) -> tuple[float, str]:
    """シグナル日の翌営業日始値"""
    for b in bars:
        if b['date'] > signal_date:
            return b['open'], b['date']
    return 0.0, ''

def calc_atr(bars: list[dict], period: int = 14) -> float:
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]['high'], bars[i]['low'], bars[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period

def analyze_trade(bars: list[dict], signal_date: str) -> dict | None:
    """
    エントリー価格・MFE・MAE・ATRストップ到達・実質結果を計算する。

    ・MFE (Max Favorable Excursion): エントリー後の最大高値到達率
    ・MAE (Max Adverse Excursion)  : エントリー後の最大安値下落率
    ・stop_hit: MAEが1.0ATRを超えたか（実際にはストップ刈られてた）
    ・real_ret : stop_hitならストップ価格での損失、そうでなければ最新終値
    """
    entry_price, entry_date = get_entry(bars, signal_date)
    if entry_price <= 0:
        return None

    # エントリー日のインデックス
    entry_idx = next((i for i, b in enumerate(bars) if b['date'] == entry_date), None)
    if entry_idx is None:
        return None

    # ATR計算（エントリー前14日）
    period = 14
    pre = bars[max(0, entry_idx - (period + 1)) : entry_idx]
    atr = calc_atr(pre, period=period)
    atr_pct    = atr / entry_price * 100 if atr > 0 else 0
    stop_price = entry_price - atr * ATR_STOP_MULT if atr > 0 else 0

    # エントリー後のバー走査
    post = bars[entry_idx:]
    if not post:
        return None

    max_high = entry_price
    min_low  = entry_price
    stop_hit      = False
    stop_hit_date = None

    for b in post:
        max_high = max(max_high, b['high'])
        min_low  = min(min_low,  b['low'])
        if not stop_hit and stop_price > 0 and b['low'] <= stop_price:
            stop_hit      = True
            stop_hit_date = b['date']

    mfe_pct = (max_high    - entry_price) / entry_price * 100
    mae_pct = (entry_price - min_low)     / entry_price * 100

    latest_close = post[-1]['close']
    latest_date  = post[-1]['date']

    # 実質リターン: ストップ到達してたらストップ価格で計算
    if stop_hit and stop_price > 0:
        real_ret = (stop_price - entry_price) / entry_price * 100
        real_outcome = 'stop'
    else:
        real_ret = (latest_close - entry_price) / entry_price * 100
        real_outcome = 'hold'

    return {
        'entry_price':    round(entry_price, 2),
        'entry_date':     entry_date,
        'latest_close':   round(latest_close, 2),
        'latest_date':    latest_date,
        'atr':            round(atr, 2),
        'atr_pct':        round(atr_pct, 2),
        'stop_price':     round(stop_price, 2),
        'mfe_pct':        round(mfe_pct, 2),   # 最大上昇幅 %
        'mae_pct':        round(mae_pct, 2),   # 最大下落幅 %
        'stop_hit':       stop_hit,            # ATRストップ到達したか
        'stop_hit_date':  stop_hit_date,
        'close_ret':      round((latest_close - entry_price) / entry_price * 100, 2),  # 終値ベース
        'real_ret':       round(real_ret, 2),  # 実態ベース（stop_hit考慮）
        'real_outcome':   real_outcome,
        'real_win':       real_ret > 0,
    }

def bucket(score: float) -> str:
    for lo, hi in [(0,30),(30,40),(40,50),(50,60),(60,70),(70,80),(80,110)]:
        if lo <= score < hi:
            return f"{lo}-{hi}"
    return "80+"

def stats(vals: list[float]) -> dict:
    if not vals:
        return {'n':0,'win_rate':0,'avg':0,'median':0,'best':0,'worst':0}
    n   = len(vals)
    srt = sorted(vals)
    med = srt[n//2] if n%2 else (srt[n//2-1]+srt[n//2])/2
    return {
        'n':       n,
        'win_rate':round(sum(1 for v in vals if v > 0)/n*100, 1),
        'avg':     round(sum(vals)/n, 2),
        'median':  round(med, 2),
        'best':    round(max(vals), 2),
        'worst':   round(min(vals), 2),
    }

# ══════════════════════════════════════════════════════════
def main():
    args = parse_args()

    # ── 対象日決定 ────────────────────────────────────────
    if args.date:
        signal_date = args.date
    else:
        files = sorted(glob.glob(str(ROOT_DIR / "frontend/public/content/strategies_history/*.json")))
        if not files:
            files = sorted(glob.glob(str(ROOT_DIR / "2???-??-??.json")))
        if not files:
            print("❌ historyファイルが見つかりません")
            sys.exit(1)
        signal_date = Path(files[0]).stem

    print(f"====== WEEKLY CHECK v2: {signal_date} ======")
    print(f"  stop={ATR_STOP_MULT}×ATR（ストップ到達判定付き）")

    # ── シグナルデータ読み込み ────────────────────────────
    candidates = [
        ROOT_DIR / "frontend/public/content/strategies_history" / f"{signal_date}.json",
        ROOT_DIR / f"{signal_date}.json",
        ROOT_DIR / "frontend/public/content" / f"{signal_date}.json",
        Path(f"/mnt/user-data/uploads/{signal_date}.json"),
    ]
    signal_file = next((p for p in candidates if p.exists()), None)
    if not signal_file:
        print(f"❌ {signal_date}.json が見つかりません")
        sys.exit(1)

    with open(signal_file, encoding='utf-8') as f:
        raw = json.load(f)
    items = raw if isinstance(raw, list) else raw.get('all_data', [])
    print(f"✅ {len(items)}銘柄のシグナルを読み込み")

    # ── SPYベースライン ───────────────────────────────────
    print("\n--- SPY（ベースライン）取得 ---")
    spy_bars = fetch_ohlc('SPY', args.no_fetch)
    spy_entry, spy_entry_date = get_entry(spy_bars, signal_date)
    spy_trade = analyze_trade(spy_bars, signal_date)
    spy_close_ret = spy_trade['close_ret'] if spy_trade else 0
    spy_latest    = spy_trade['latest_close'] if spy_trade else 0
    spy_latest_date = spy_trade['latest_date'] if spy_trade else ''
    print(f"SPY: {spy_entry_date}始値 ${spy_entry:.2f} → ${spy_latest:.2f} ({spy_close_ret:+.2f}%)")

    # ── 各銘柄処理 ───────────────────────────────────────
    print(f"\n--- {len(items)}銘柄のOHLC取得・分析 ---")
    results = []
    ohlc_cache = {}

    for i, item in enumerate(items):
        ticker    = item['ticker']
        scores    = item.get('scores', {})
        status    = item.get('status', '')
        composite = scores.get('composite', 0)
        vcp       = scores.get('vcp', 0)
        rs        = scores.get('rs', 0)
        ecr       = scores.get('ecr_rank', 0)
        canslim   = scores.get('canslim', 0)

        if ticker not in ohlc_cache:
            ohlc_cache[ticker] = fetch_ohlc(ticker, args.no_fetch)
            if (i+1) % 50 == 0:
                stop_hits = sum(1 for r in results if r.get('stop_hit'))
                print(f"  [{i+1}/{len(items)}] 有効:{len(results)}件 ストップ到達:{stop_hits}件")

        bars = ohlc_cache[ticker]
        if not bars:
            continue

        trade = analyze_trade(bars, signal_date)
        if not trade:
            continue

        alpha_close = trade['close_ret'] - spy_close_ret
        alpha_real  = trade['real_ret']  - spy_close_ret

        results.append({
            'ticker':     ticker,
            'status':     status,
            'composite':  composite,
            'vcp':        vcp,
            'rs':         rs,
            'ecr':        ecr,
            'canslim':    canslim,
            **trade,
            'alpha_close': round(alpha_close, 2),
            'alpha_real':  round(alpha_real,  2),
        })

    stop_count = sum(1 for r in results if r['stop_hit'])
    print(f"\n✅ 有効銘柄: {len(results)}件")
    print(f"   終値ベース勝ち: {sum(1 for r in results if r['close_ret']>0)}件")
    print(f"   実態ベース勝ち: {sum(1 for r in results if r['real_win'])}件")
    print(f"   ストップ到達:   {stop_count}件 ({stop_count/len(results)*100:.1f}%)")

    # ── スコア帯別集計 ───────────────────────────────────
    def analyze_by_score(key):
        buckets_close = defaultdict(list)
        buckets_real  = defaultdict(list)
        buckets_mfe   = defaultdict(list)
        buckets_mae   = defaultdict(list)
        buckets_alpha = defaultdict(list)
        buckets_stop  = defaultdict(list)

        for r in results:
            b = bucket(r[key])
            buckets_close[b].append(r['close_ret'])
            buckets_real[b].append(r['real_ret'])
            buckets_mfe[b].append(r['mfe_pct'])
            buckets_mae[b].append(r['mae_pct'])
            buckets_alpha[b].append(r['alpha_real'])
            buckets_stop[b].append(1 if r['stop_hit'] else 0)

        out = {}
        for b in sorted(buckets_close.keys()):
            n = len(buckets_close[b])
            out[b] = {
                'n':            n,
                'close':        stats(buckets_close[b]),
                'real':         stats(buckets_real[b]),
                'mfe':          stats(buckets_mfe[b]),
                'mae':          stats(buckets_mae[b]),
                'alpha':        stats(buckets_alpha[b]),
                'stop_hit_rate':round(sum(buckets_stop[b])/n*100, 1),
            }
        return out

    score_analysis = {k: analyze_by_score(k) for k in ['composite','vcp','rs','ecr','canslim']}

    # ── STATUS別 ─────────────────────────────────────────
    status_analysis = {}
    for st in ['ACTION', 'WAIT']:
        sub = [r for r in results if r['status'] == st]
        if sub:
            status_analysis[st] = {
                'n':           len(sub),
                'close':       stats([r['close_ret'] for r in sub]),
                'real':        stats([r['real_ret']  for r in sub]),
                'mfe':         stats([r['mfe_pct']   for r in sub]),
                'mae':         stats([r['mae_pct']   for r in sub]),
                'stop_hit_rate': round(sum(1 for r in sub if r['stop_hit'])/len(sub)*100, 1),
            }

    # ── コンソール出力 ───────────────────────────────────
    print(f"\n=== composite スコア帯別 実態リターン ===")
    print(f"{'帯':8s} {'n':>4s} {'終値%':>7s} {'実態%':>7s} {'MFE%':>7s} {'MAE%':>7s} {'Stop率':>7s}")
    for b, s in sorted(score_analysis['composite'].items()):
        if s['n'] >= 5:
            print(f"{b:8s} {s['n']:4d} "
                  f"{s['close']['avg']:+7.2f} "
                  f"{s['real']['avg']:+7.2f} "
                  f"{s['mfe']['avg']:+7.2f} "
                  f"{s['mae']['avg']:+7.2f} "
                  f"{s['stop_hit_rate']:6.1f}%")

    # ── 書き出し ─────────────────────────────────────────
    sorted_results = sorted(results, key=lambda x: x['real_ret'], reverse=True)

    output = {
        'generated_at': datetime.now().isoformat(),
        'signal_date':  signal_date,
        'eval_date':    spy_latest_date,
        'hold_days':    (datetime.strptime(spy_latest_date,'%Y-%m-%d') -
                         datetime.strptime(signal_date,'%Y-%m-%d')).days if spy_latest_date else 0,
        'stop_atr_mult': ATR_STOP_MULT,
        'spy': {
            'entry_price':  round(spy_entry, 2),
            'latest_price': round(spy_latest, 2),
            'close_ret':    round(spy_close_ret, 2),
        },
        'summary': {
            'total':          len(results),
            'close_win_rate': round(sum(1 for r in results if r['close_ret']>0)/len(results)*100, 1),
            'real_win_rate':  round(sum(1 for r in results if r['real_win'])/len(results)*100, 1),
            'avg_close_ret':  round(sum(r['close_ret'] for r in results)/len(results), 2),
            'avg_real_ret':   round(sum(r['real_ret']  for r in results)/len(results), 2),
            'avg_mfe':        round(sum(r['mfe_pct']   for r in results)/len(results), 2),
            'avg_mae':        round(sum(r['mae_pct']   for r in results)/len(results), 2),
            'stop_hit_rate':  round(stop_count/len(results)*100, 1),
            'beat_spy_close': round(sum(1 for r in results if r['alpha_close']>0)/len(results)*100, 1),
            'beat_spy_real':  round(sum(1 for r in results if r['alpha_real'] >0)/len(results)*100, 1),
        },
        'by_status':  status_analysis,
        'by_score':   score_analysis,
        'top10':      sorted_results[:10],
        'bottom10':   sorted_results[-10:],
        'all_results':sorted_results,
    }

    # ── 従来通り weekly_check.json に上書き（フォールバック用）
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n✅ 保存: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size//1024}KB)")

    # ── 日付付きファイルにも保存（累積蓄積用）
    slug = f"backtest-{signal_date}"
    dated_file = OUTPUT_DIR / f"{slug}.json"
    dated_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✅ 累積保存: {dated_file}")

    # ── index.json を更新（既存エントリがあれば上書き、なければ追記）
    index_file = OUTPUT_DIR / "index.json"
    try:
        index = json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else {"articles": []}
    except Exception:
        index = {"articles": []}

    new_entry = {
        "slug":         slug,
        "type":         "backtest",
        "date":         signal_date,
        "published_at": output["generated_at"],
        "title_ja":     f"{signal_date} バックテスト — ACTION勝率{output['summary']['real_win_rate']}% / {output['summary']['total']}銘柄"
    }
    # 同じslugがあれば置き換え、なければ先頭に追加
    articles = [a for a in index.get("articles", []) if a.get("slug") != slug]
    articles.insert(0, new_entry)
    index["articles"] = articles
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✅ index.json 更新: {len(articles)}件")

    print("====== 完了 ======")

if __name__ == '__main__':
    main()
