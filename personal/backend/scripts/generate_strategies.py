#!/usr/bin/env python3
"""
scripts/generate_strategies.py — 最適化版（1回計算・3ファイル出力）
=====================================================================
変更点:
- 計算は1回のみ
- 詳細データを全て保持
- 3種類のJSON同時生成（用途別）

出力ファイル:
1. strategies.json         → フルデータ + ランキング（Dashboard/Scanner）
2. strategies_history/{date}.json → スコアのみ（履歴チャート用）
3. logs/full_data_{date}.json     → 完全版（バックアップ・詳細分析用）

実行時間: 5-10分（600銘柄）
API呼び出し: 600回のみ（最適化済み）
"""
import os, sys, json, time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(str(Path(__file__).parent.parent / "shared"))
from engines import core_fmp
from engines.analysis import VCPAnalyzer, RSAnalyzer
from engines.canslim import CANSLIMAnalyzer
from engines.ecr_strategy import ECRStrategyEngine
from engines.sentinel_efficiency import SentinelEfficiencyAnalyzer
from engines.config import TICKERS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(r"D:\program\personal\frontend\public\content")
HISTORY_DIR = OUTPUT_DIR / "strategies_history"
LOG_DIR = PROJECT_ROOT / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 流動性フィルター基準
MIN_VOLUME = 400_000
MIN_PRICE = 15.0
MIN_MARKET_CAP = 200_000_000

MAX_WORKERS = 2


def process_ticker(ticker: str) -> dict:
    """
    1銘柄の完全分析
    
    Returns:
        {
            'ticker': 'NVDA',
            'name': 'NVIDIA Corporation',
            'sector': 'Technology',
            'price': 880.50,
            'avg_volume': 45000000,
            'market_cap': 2180000000000,
            'scores': {...},
            'vcp_details': {...},
            'ses_details': {...},
            'ecr_phase': 'ACCUMULATION',
            'canslim_grade': 'A',
            'status': 'ACTION',
            'pivot': 900.0,
            'pivot_dist_pct': -2.17,
            'ma50_ratio': 5.2,
            'ma200_ratio': 12.8,
            'atr_pct': 2.5,
        }
    """
    try:
        # 1. 過去株価取得
        df = core_fmp.get_historical_data(ticker, days=400)
        if df is None or len(df) < 200:
            return None
        
        # 2. プロファイル取得
        profile = core_fmp.get_company_profile(ticker) or {}
        
        # 3. 各手法スコア計算
        vcp = VCPAnalyzer.calculate(df)
        rs_raw = RSAnalyzer.get_raw_score(df)
        canslim = CANSLIMAnalyzer.calculate(ticker, df)
        ecr = ECRStrategyEngine.analyze_single(ticker, df)
        ses = SentinelEfficiencyAnalyzer.calculate(df)
        
        # 4. 価格・出来高データ
        price = float(df["Close"].iloc[-1])
        pivot = float(df["High"].iloc[-20:].max())
        avg_volume = int(df["Volume"].iloc[-50:].mean()) if len(df) >= 50 else 0
        market_cap = profile.get("mktCap", 0)
        
        # 5. ステータス判定
        dist = (price - pivot) / pivot
        status = "ACTION" if -0.05 <= dist <= 0.03 else ("WAIT" if dist < -0.05 else "EXTENDED")
        
        # 6. MA比率
        ma50 = df["Close"].rolling(50).mean().iloc[-1]
        ma200 = df["Close"].rolling(200).mean().iloc[-1]
        ma50_ratio = round((price / ma50 - 1) * 100, 1) if ma50 > 0 else 0.0
        ma200_ratio = round((price / ma200 - 1) * 100, 1) if ma200 > 0 else 0.0
        
        # 7. ATR
        atr = vcp.get("atr", 0)
        atr_pct = round(atr / price * 100, 2) if price > 0 else 0.0
        
        # 8. Portfolio Factor（VCPシグナルの質）
        pf = len([s for s in vcp.get("signals", []) if "Pivot" in s or "Tight" in s]) * 1.25
        
        return {
            "ticker": ticker,
            "raw_rs": rs_raw,
            "data": {
                # 基本情報
                "ticker": ticker,
                "name": profile.get("companyName", ticker)[:30],
                "sector": profile.get("sector", "N/A"),
                "industry": profile.get("industry", "N/A")[:30],
                
                # 価格データ
                "price": round(price, 2),
                "pivot": round(pivot, 2),
                "pivot_dist_pct": round(dist * 100, 2),
                "status": status,
                
                # 流動性データ
                "avg_volume": avg_volume,
                "market_cap": market_cap,
                
                # スコア
                "scores": {
                    "vcp": vcp["score"],
                    "rs": 0,  # 後で全体percentile計算
                    "ses": ses["score"],
                    "ecr_rank": ecr["sentinel_rank"],
                    "canslim": canslim["score"],
                    "pf": round(pf, 2),
                    "composite": 0,  # 後で計算
                },
                
                # 詳細データ
                "vcp_details": vcp,
                "ses_details": ses,
                "ecr_phase": ecr["phase"],
                "ecr_strategy": ecr["strategy"],
                "canslim_grade": canslim["grade"],
                "canslim_metrics": canslim["metrics"],
                
                # テクニカル指標
                "ma50_ratio": ma50_ratio,
                "ma200_ratio": ma200_ratio,
                "atr_pct": atr_pct,
            }
        }
    
    except Exception as e:
        print(f"    ❌ {ticker}: {e}")
        return None


def calculate_rs_percentiles(results: list) -> dict:
    """RS percentile計算（全銘柄の相対順位）"""
    rs_values = [(r["ticker"], r["raw_rs"]) for r in results if r["raw_rs"] != -999.0]
    rs_values.sort(key=lambda x: x[1], reverse=True)
    
    rs_map = {}
    for rank, (ticker, _) in enumerate(rs_values):
        percentile = int((1 - rank / len(rs_values)) * 99)
        rs_map[ticker] = percentile
    
    return rs_map


def finalize_scores(results: list, rs_map: dict) -> list:
    """最終スコア計算（RS + Composite）"""
    final = []
    
    for r in results:
        d = r["data"]
        ticker = r["ticker"]
        
        # RS percentile設定
        rs = rs_map.get(ticker, 0)
        d["scores"]["rs"] = rs
        
        # Composite score計算
        vcp_rs_norm = min(100, (d["scores"]["vcp"] / 105 * 50) + (rs / 99 * 50))
        composite = (
            vcp_rs_norm * 0.35 +
            d["scores"]["ecr_rank"] * 0.35 +
            d["scores"]["canslim"] * 0.30
        )
        d["scores"]["composite"] = round(composite, 1)
        
        # 手法ヒット数
        d["method_hits"] = sum([
            d["scores"]["vcp"] >= 70 and rs >= 80,
            d["scores"]["ecr_rank"] >= 70,
            d["scores"]["canslim"] >= 60,
            d["scores"]["ses"] >= 60,
        ])
        
        final.append(d)
    
    return final


def build_rankings(data: list) -> dict:
    """
    ランキング生成（流動性フィルター付き）
    
    Returns:
        {
            'vcp_rs': [top30],
            'ecr': [top30],
            'canslim': [top30],
            'ses': [top30],
            'composite': [top30],
            'consensus': [top30],
        }
    """
    # 流動性フィルター
    liquid = []
    excluded_count = {"volume": 0, "price": 0, "market_cap": 0}
    
    for item in data:
        if item["status"] not in ("ACTION", "WAIT"):
            continue
        
        if item["avg_volume"] < MIN_VOLUME:
            excluded_count["volume"] += 1
            continue
        
        if item["price"] < MIN_PRICE:
            excluded_count["price"] += 1
            continue
        
        if item["market_cap"] > 0 and item["market_cap"] < MIN_MARKET_CAP:
            excluded_count["market_cap"] += 1
            continue
        
        liquid.append(item)
    
    print(f"\n📊 流動性フィルター: {len(data)} → {len(liquid)}銘柄")
    print(f"   除外: 出来高{excluded_count['volume']} / 株価{excluded_count['price']} / 時価総額{excluded_count['market_cap']}")
    
    def top(key_fn, n=30):
        return sorted(liquid, key=key_fn, reverse=True)[:n]
    
    return {
        "vcp_rs": top(lambda r: r["scores"]["vcp"] * 0.5 + r["scores"]["rs"] * 0.5),
        "ecr": top(lambda r: r["scores"]["ecr_rank"]),
        "canslim": top(lambda r: r["scores"]["canslim"]),
        "ses": top(lambda r: r["scores"]["ses"]),
        "composite": top(lambda r: r["scores"]["composite"]),
        "consensus": sorted(liquid, key=lambda r: (r["method_hits"], r["scores"]["composite"]), reverse=True)[:30],
    }


def build_phase_summary(data: list) -> dict:
    """ECRフェーズ別サマリー"""
    phases = {}
    for r in data:
        p = r.get("ecr_phase", "WATCH")
        if p not in phases:
            phases[p] = []
        phases[p].append(r)
    
    return {p: sorted(v, key=lambda x: x["scores"]["ecr_rank"], reverse=True)[:20] 
            for p, v in phases.items()}


def build_sector_summary(data: list) -> list:
    """セクター別サマリー"""
    sectors = {}
    for r in data:
        s = r.get("sector", "N/A")
        if s not in sectors:
            sectors[s] = []
        sectors[s].append(r)
    
    summary = []
    for sector, items in sectors.items():
        summary.append({
            "sector": sector,
            "count": len(items),
            "avg_vcp": round(sum(x["scores"]["vcp"] for x in items) / len(items), 1),
            "avg_composite": round(sum(x["scores"]["composite"] for x in items) / len(items), 1),
            "top_ticker": sorted(items, key=lambda x: x["scores"]["composite"], reverse=True)[0]["ticker"],
        })
    
    return sorted(summary, key=lambda x: x["avg_composite"], reverse=True)


def save_outputs(data: list, rankings: dict, phases: dict, sectors: list):
    """3種類のJSONファイル出力"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # ========================================
    # 1. strategies.json（フルデータ + ランキング）
    # ========================================
    strategies = {
        "generated_at": date_str,
        "ticker_count": len(data),
        "action_count": sum(1 for r in data if r["status"] == "ACTION"),
        "wait_count": sum(1 for r in data if r["status"] == "WAIT"),
        "rankings": rankings,
        "ecr_phases": phases,
        "sectors": sectors[:10],
        "all_data": data,  # 全銘柄フルデータ
    }
    
    strategies_file = OUTPUT_DIR / "strategies.json"
    strategies_file.write_text(json.dumps(strategies, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"\n✅ strategies.json 生成: {len(data)}銘柄")
    
    # ========================================
    # 2. strategies_history/{date}.json（簡易版）
    # ========================================
    history_simple = [
        {
            "ticker": r["ticker"],
            "scores": r["scores"],
            "status": r["status"],
        }
        for r in data
    ]
    
    history_file = HISTORY_DIR / f"{date_str}.json"
    history_file.write_text(json.dumps(history_simple, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✅ 履歴保存: {history_file.name}")
    
    # ========================================
    # 3. logs/full_data_{date}.json（完全版バックアップ）
    # ========================================
    log_file = LOG_DIR / f"full_data_{date_str}.json"
    log_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✅ ログ保存: {log_file.name}")
    
    # 30日以上前の履歴削除
    cleanup_old_history()


def cleanup_old_history():
    """30日以上前の履歴ファイル削除"""
    cutoff = time.time() - (30 * 86400)
    deleted = 0
    
    for f in HISTORY_DIR.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    
    if deleted > 0:
        print(f"   古い履歴削除: {deleted}ファイル")


def main():
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   📊 SENTINEL STRATEGIES GENERATOR (Optimized)               ║
║                                                               ║
║   1回計算 → 3ファイル同時生成                                ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    print(f"対象: {len(TICKERS)}銘柄")
    print(f"並列処理: {MAX_WORKERS}スレッド")
    print(f"予想時間: {len(TICKERS) * 0.3 / 60 / MAX_WORKERS:.1f}分")
    
    # 1. 全銘柄計算
    print(f"\n🔍 分析開始...")
    start = time.time()
    
    raw_results = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_ticker, t): t for t in TICKERS}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                raw_results.append(result)
            
            if len(raw_results) % 50 == 0:
                print(f"   進捗: {len(raw_results)}/{len(TICKERS)}")
    
    elapsed = time.time() - start
    print(f"\n✅ 分析完了: {len(raw_results)}/{len(TICKERS)}銘柄 ({elapsed/60:.1f}分)")
    
    # 2. RS percentile計算
    print(f"\n📊 RS percentile計算中...")
    rs_map = calculate_rs_percentiles(raw_results)
    
    # 3. 最終スコア計算
    data = finalize_scores(raw_results, rs_map)
    
    # 4. ランキング生成
    print(f"\n🏆 ランキング生成中...")
    rankings = build_rankings(data)
    
    # 5. フェーズ別サマリー
    phases = build_phase_summary(data)
    
    # 6. セクター別サマリー
    sectors = build_sector_summary(data)
    
    # 7. 3ファイル出力
    save_outputs(data, rankings, phases, sectors)
    
    # 8. サマリー表示
    print(f"\n{'='*60}")
    print(f"📊 Composite Top10:")
    for i, item in enumerate(rankings["composite"][:10], 1):
        print(f"   {i}. {item['ticker']:<6} {item['scores']['composite']:>5.1f}  "
              f"VCP:{item['scores']['vcp']:>3} RS:{item['scores']['rs']:>2} "
              f"ECR:{item['scores']['ecr_rank']:>2}")
    
    print(f"\n{'='*60}")
    print(f"✅ 完了: {elapsed/60:.1f}分")


if __name__ == "__main__":
    main()