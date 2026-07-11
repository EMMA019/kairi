#!/usr/bin/env python3
"""
scripts/refresh_tickers.py — 楽天4553 → 流動性Top600更新スクリプト（1000件ごと途中バックアップ版）
"""
import os, sys, json, time, re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(str(Path(__file__).parent.parent / "shared"))
from engines import core_fmp

ROOT = Path(__file__).resolve().parent.parent
RAKUTEN_FILE = ROOT / "data" / "rakuten_tickers.txt"
CONFIG_FILE = ROOT / "shared" / "engines" / "config.py"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

MIN_VOLUME = 300_000
MIN_PRICE = 15.0
MIN_MARKET_CAP = 100_000_000
TARGET = 600
MAX_WORKERS = 5
BASE_SLEEP = 0.5


def load_tickers():
    if not RAKUTEN_FILE.exists():
        print(f"❌ {RAKUTEN_FILE} が見つかりません")
        sys.exit(1)
    
    tickers = []
    with open(RAKUTEN_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            t = line.strip().upper()
            if t and not t.startswith('#'):
                if '.' in t or t.endswith('.B') or t.endswith('.A'):
                    continue
                tickers.append(t)
    
    print(f"📄 楽天リスト: {len(tickers)}銘柄")
    return tickers


def get_liquidity(ticker: str):
    try:
        df = core_fmp.get_historical_data(ticker, days=35)
        if df is None or len(df) < 20:
            return None
        
        recent_df = df.tail(30)
        avg_vol = int(recent_df["Volume"].mean())
        price = df["Close"].iloc[-1] if len(df) > 0 else 0
        
        q_data = core_fmp._get(f"{core_fmp.BASE_URL}/quote", {"symbol": ticker})
        cap = q_data[0].get("marketCap", 0) if q_data and isinstance(q_data, list) and q_data else 0
        
        score = (avg_vol / 1_000_000) * 0.4 + price * 0.3 + (cap / 1_000_000_000) * 0.3
        
        time.sleep(BASE_SLEEP)
        
        return {
            'ticker': ticker,
            'avg_volume': avg_vol,
            'price': round(price, 2),
            'market_cap': cap,
            'score': round(score, 2),
        }
    except Exception as e:
        print(f"ERROR {ticker}: {e}")
        return None


def save_temp_backup(results, failed, processed):
    """1000件ごとに途中バックアップを作成"""
    if processed % 1000 != 0:
        return
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file = LOG_DIR / f"temp_refresh_{processed}_{ts}.json"
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "processed": processed,
        "results_count": len(results),
        "failed_count": len(failed),
        "tickers": [r['ticker'] for r in results],
        "failed": failed
    }
    
    temp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"   💾 途中バックアップ作成: {temp_file.name}")


def scan(tickers):
    print(f"\n🔍 スキャン開始: {len(tickers)}銘柄 (並列 {MAX_WORKERS} workers, sleep {BASE_SLEEP}s)")
    
    results = []
    failed = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(get_liquidity, t): t for t in tickers}
        
        for future in as_completed(future_to_ticker):
            t = future_to_ticker[future]
            data = future.result()
            if data:
                results.append(data)
            else:
                failed.append(t)
            
            processed = len(results) + len(failed)
            
            # 1000件ごとに途中バックアップ
            save_temp_backup(results, failed, processed)
            
            if processed % 100 == 0:
                fail_rate = len(failed) / processed * 100 if processed > 0 else 0
                print(f"   {processed}件処理済み / 取得: {len(results)} / 失敗: {len(failed)} ({fail_rate:.1f}%)")
    
    print(f"✅ 完了: 取得 {len(results)}銘柄 / 失敗 {len(failed)}銘柄")
    return results, failed


def filter_rank(data):
    print(f"\n📊 フィルター適用")
    
    ok = []
    ng = []
    
    for d in data:
        bad = []
        if d['avg_volume'] < MIN_VOLUME:
            bad.append(f'出来高 ({d["avg_volume"]:,})')
        if d['price'] < MIN_PRICE:
            bad.append(f'株価 ({d["price"]})')
        if d['market_cap'] < MIN_MARKET_CAP:
            bad.append(f'時価総額 ({d["market_cap"]:,})')
        
        if bad:
            ng.append({'ticker': d['ticker'], 'reasons': bad})
        else:
            ok.append(d)
    
    print(f"   OK: {len(ok)} / NG: {len(ng)}")
    
    ranked = sorted(ok, key=lambda x: x['score'], reverse=True)
    selected = ranked[:TARGET]
    extra = ranked[TARGET:]
    
    print(f"   選定: {len(selected)}銘柄")
    return selected, ng, extra


def update_config(tickers):
    print(f"\n📝 config.py更新")
    
    # 既存バックアップを安全に削除
    bak_file = CONFIG_FILE.with_suffix('.py.bak')
    if bak_file.exists():
        bak_file.unlink()
    
    content = CONFIG_FILE.read_text(encoding='utf-8')
    
    lines = []
    for i in range(0, len(tickers), 10):
        chunk = tickers[i:i+10]
        lines.append('    ' + ', '.join([f'"{t}"' for t in chunk]))
    
    new_tickers = 'TICKERS = [\n' + ',\n'.join(lines) + '\n]'
    
    pattern = r'TICKERS\s*=\s*\[.*?\]'
    new_content = re.sub(pattern, new_tickers, content, flags=re.DOTALL | re.MULTILINE)
    
    # タイムスタンプ付きバックアップ作成
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = CONFIG_FILE.with_name(f"config_{ts}.py.bak")
    CONFIG_FILE.rename(backup_file)
    
    CONFIG_FILE.write_text(new_content, encoding='utf-8')
    print(f"   ✅ 更新完了（バックアップ: config_{ts}.py.bak）")


def save_log(sel, ng, ex, fail):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log = LOG_DIR / f"refresh_{ts}.json"
    
    reasons = {}
    for x in ng:
        for r in x['reasons']:
            reasons[r] = reasons.get(r, 0) + 1
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "selected": len(sel),
        "excluded": len(ng),
        "rank_out": len(ex),
        "failed": len(fail),
        "tickers": [s['ticker'] for s in sel],
        "top10": sel[:10],
        "reasons": reasons,
    }
    
    log.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    print(f"\n{'='*50}")
    print(f"結果: 選定{len(sel)} / 除外{len(ng)} / ランク外{len(ex)} / 失敗{len(fail)}")
    if reasons:
        print("除外理由:")
        for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {r}: {c}")
    print(f"{'='*50}\n")


def main():
    print("""
╔════════════════════════════════════════╗
║  🔄 TICKER REFRESH (Weekly)           ║
║  楽天4553 → 流動性Top600              ║
╚════════════════════════════════════════╝
""")
    
    tickers = load_tickers()
    data, failed = scan(tickers)
    
    if len(data) == 0:
        print("❌ 失敗")
        sys.exit(1)
    
    sel, ng, ex = filter_rank(data)
    
    update_config([s['ticker'] for s in sel])
    save_log(sel, ng, ex, failed)
    
    print(f"✅ config.py更新完了")


if __name__ == "__main__":
    main()