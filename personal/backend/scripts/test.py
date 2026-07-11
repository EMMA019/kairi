#!/usr/bin/env python3
"""
generate_historical_20yf_simple.py — 超シンプル版（確実にファイル生成）
FMP完全排除・yfinanceのみ・固定20銘柄
"""
import sys, json, time
from pathlib import Path
from datetime import datetime, timedelta

import yfinance as yf

sys.path.append(str(Path(__file__).parent.parent / "shared"))

from engines.analysis import VCPAnalyzer, RSAnalyzer
from engines.canslim import CANSLIMAnalyzer
from engines.ecr_strategy import ECRStrategyEngine
from engines.sentinel_efficiency import SentinelEfficiencyAnalyzer

# ====================== 固定20銘柄 ======================
FIXED_TICKERS = [
    "SMH", "WMT", "MRSH", "RGLD", "SHEL", "ELV", "INTU", "KMB", "BABA", "ZTS",
    "GEV", "QQQ", "CRWD", "PNC", "SLV", "VCIT", "JPM", "BP", "APH", "MO"
]

OUTPUT_DIR = Path(__file__).parent.parent / "frontend" / "public" / "content" / "strategies_history"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SLEEP_SECONDS = 3.5

def generate_for_date(target_date: str):
    print(f"\n📅 {target_date} 処理中...")

    results = []
    for ticker in FIXED_TICKERS:
        try:
            df = yf.download(ticker, period="300d", interval="1d", progress=False)
            if len(df) < 130:
                continue

            # 本物のエンジンを使用
            vcp = VCPAnalyzer.calculate(df)
            rs_raw = RSAnalyzer.get_raw_score(df)
            rs_pct = min(99, max(0, int((rs_raw + 0.3) * 100))) if rs_raw != -999.0 else 0

            canslim = CANSLIMAnalyzer.calculate(ticker, df)
            ecr = ECRStrategyEngine.analyze_single(ticker, df)
            ses = SentinelEfficiencyAnalyzer.calculate(df)

            price = float(df["Close"].iloc[-1])
            pivot = float(df["High"].iloc[-50:].max())
            dist_pct = round((price - pivot) / pivot * 100, 2)

            results.append({
                "ticker": ticker,
                "scores": {
                    "vcp": vcp["score"],
                    "rs": rs_pct,
                    "canslim": canslim["score"],
                    "ecr_rank": ecr["sentinel_rank"],
                    "ses": ses["score"],
                    "composite": round(vcp["score"]*0.35 + rs_pct*0.35 + canslim["score"]*0.3, 1)
                },
                "status": "ACTION" if dist_pct <= 5 and vcp["score"] >= 55 else "WAIT",
                "vcp_details": vcp,
                "ses_details": ses,
                "ecr_phase": ecr["phase"]
            })

        except Exception as e:
            print(f"  ⚠️ {ticker} エラー: {e}")

        time.sleep(SLEEP_SECONDS)

    # 保存（空でもファイルを作る）
    file_path = OUTPUT_DIR / f"{target_date}.json"
    file_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✅ {target_date} 保存完了 ({len(results)}銘柄)")


if __name__ == "__main__":
    start_date = "2025-11-01"
    end_date   = "2026-02-18"

    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    print("=== シンプル版 過去データ生成開始 ===\n")

    while current <= end:
        generate_for_date(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    print("🎉 全期間の生成が完了しました！")