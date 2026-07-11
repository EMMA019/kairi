"""
sentinel_efficiency.py
======================
SENTINEL EFFICIENCY SCORE (SES)
機関投資家による「効率的な買い集め」と「売り枯れ」を定量化する。

4つの指標で構成（合計100点満点）:
  Fractal Efficiency (30pt) — 価格の効率的な移動（ノイズ除去）
  True Force Index   (30pt) — 買い出来高 vs 売り出来高の比率
  Volatility Squeeze (20pt) — ボラティリティ収縮（VCPと相補的）
  Bar Quality        (20pt) — 終値が高値側で引けているか（CLV）
"""
import pandas as pd
import numpy as np


class SentinelEfficiencyAnalyzer:

    @staticmethod
    def calculate(df: pd.DataFrame, period: int = 20) -> dict:
        try:
            if df is None or len(df) < period + 40:
                return SentinelEfficiencyAnalyzer._empty_result()

            close  = df["Close"]
            open_  = df["Open"]
            high   = df["High"]
            low    = df["Low"]
            volume = df["Volume"]

            # ── 1. Fractal Efficiency (30pt) ─────────────────────
            # 価格が「まっすぐ」動いているか（Kaufman ER）
            net_change = abs(float(close.iloc[-1]) - float(close.iloc[-period]))
            sum_moves  = float(close.diff().abs().iloc[-period:].sum())
            er = net_change / sum_moves if sum_moves > 0 else 0.0

            er_score = (
                30 if er > 0.60 else
                25 if er > 0.50 else
                20 if er > 0.40 else
                10 if er > 0.30 else 0
            )

            # ── 2. True Force Index (30pt) ─────────────────────
            # 出来高×価格変化 — 買い圧力 vs 売り圧力
            price_change  = close.diff()
            force         = volume * price_change
            subset_force  = force.iloc[-period:]
            pos_force     = float(subset_force[subset_force > 0].sum())
            neg_force     = float(abs(subset_force[subset_force < 0].sum()))
            total_force   = pos_force + neg_force
            force_ratio   = pos_force / total_force if total_force > 0 else 0.5

            vol_score = (
                30 if force_ratio > 0.80 else
                20 if force_ratio > 0.65 else
                10 if force_ratio > 0.55 else 0
            )

            # ── 3. Volatility Squeeze (20pt) ─────────────────────
            # 直近ボラ vs 過去ボラ（小さいほど収縮 → 高スコア）
            returns         = close.pct_change()
            curr_vol        = float(returns.iloc[-period:].std())
            past_vol        = float(returns.iloc[-60:-period].std()) if len(returns) >= 60 else curr_vol
            vol_contraction = curr_vol / past_vol if past_vol > 0 else 1.0

            sqz_score = (
                20 if vol_contraction < 0.50 else
                15 if vol_contraction < 0.65 else
                10 if vol_contraction < 0.80 else
                -5 if vol_contraction > 1.20 else 0
            )

            # ── 4. Bar Quality / CLV (20pt) ──────────────────────
            # 終値が高値側で引けているか（大陽線の質）
            hl_range  = (high - low).replace(0, np.nan)
            clv       = ((close - low) / hl_range).fillna(0.5)
            body_str  = ((close - open_) / hl_range).fillna(0.0)
            avg_clv   = float(clv.iloc[-period:].mean())
            avg_body  = float(body_str.iloc[-period:].mean())

            bar_score = (
                20 if avg_clv > 0.60 and avg_body > 0.10 else
                15 if avg_clv > 0.55 and avg_body > 0.00 else
                10 if avg_clv > 0.50 else 0
            )

            total = er_score + vol_score + sqz_score + bar_score
            return {
                "score": int(max(0, min(100, total))),
                "metrics": {
                    "er":              round(er, 3),
                    "force_ratio":     round(force_ratio, 3),
                    "vol_contraction": round(vol_contraction, 3),
                    "avg_clv":         round(avg_clv, 3),
                },
                "breakdown": {
                    "fractal_efficiency": er_score,
                    "true_force":         vol_score,
                    "volatility_squeeze": sqz_score,
                    "bar_quality":        bar_score,
                },
            }
        except Exception:
            return SentinelEfficiencyAnalyzer._empty_result()

    @staticmethod
    def _empty_result() -> dict:
        return {
            "score": 0,
            "metrics": {
                "er": 0.0, "force_ratio": 0.5,
                "vol_contraction": 1.0, "avg_clv": 0.5,
            },
            "breakdown": {
                "fractal_efficiency": 0, "true_force": 0,
                "volatility_squeeze": 0, "bar_quality": 0,
            },
        }
