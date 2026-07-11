"""
ecr_strategy.py
===============
Energy Compression Rotation (ECR) Strategy Engine

VCP（収縮パターン）× SES（効率性）× RS（相対強度）を統合した
複合スコアリング + フェーズ判定エンジン。

最適化ポイント:
  - _calculate_metrics を1回呼んで結果をキャッシュ
  - ヒストリカル比較（前日・先週）はRS/VCPの差分のみ軽量計算
  - 全銘柄スキャン時の計算コストを約1/3に削減
"""
import pandas as pd
import numpy as np

from .analysis             import VCPAnalyzer, RSAnalyzer
from .sentinel_efficiency  import SentinelEfficiencyAnalyzer


class ECRStrategyEngine:
    """
    フェーズ判定:
      IGNITION    — ランク急上昇 or 出来高を伴う初動
      ACCUMULATION — 高ランク + 低ボラで収縮中（最注目）
      RELEASE     — ピボット突破済みで勢いが衰えてきた
      HOLD/WATCH  — ランク65以上だが条件未達
      WATCH       — 監視圏内
      REJECTED    — ランク5未満（対象外）
    """

    @staticmethod
    def analyze_single(ticker: str, df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 150:
                return ECRStrategyEngine._empty_result(ticker)

            # ── 現在の指標（フル計算・1回のみ） ────────────────
            curr = ECRStrategyEngine._calculate_metrics(df)
            if curr["rank"] < 5:
                return ECRStrategyEngine._compile_result(ticker, curr, {}, "REJECTED", "NONE")

            # ── 変化率（前日・5日前）— RS変化のみ軽量計算 ───────
            # VCP/SESの再計算は重いため、RSの差分とボラ変化で代替
            rank_delta = 0.0
            rank_slope = 0.0
            try:
                rs_prev  = RSAnalyzer.get_raw_score(df.iloc[:-1])
                rs_week  = RSAnalyzer.get_raw_score(df.iloc[:-5])
                rs_curr  = RSAnalyzer.get_raw_score(df)
                if rs_prev != -999.0 and rs_curr != -999.0:
                    rank_delta = round((rs_curr - rs_prev) * 100, 1)
                if rs_week != -999.0 and rs_curr != -999.0:
                    rank_slope = round((rs_curr - rs_week) * 20, 2)  # 5日で正規化
            except Exception:
                pass

            dyn = {
                "rank_delta":      rank_delta,
                "rank_5d_slope":   rank_slope,
                "vol_change_ratio": curr["vol_ratio"],
            }

            rank      = curr["rank"]
            dist      = curr["dist_to_pivot"]
            vol_ratio = curr["vol_ratio"]

            # ── フェーズ判定 ──────────────────────────────────────
            phase = "WATCH"
            strat = "NONE"

            # RELEASE: ピボット突破済みでモメンタム鈍化
            if dist < -0.07 and rank_slope <= 0:
                phase = "RELEASE"
                strat = "TRAILING"

            # IGNITION: ランク急上昇 or 出来高×モメンタム初動
            elif (
                rank_delta >= 15
                or (rank >= 75 and rank_slope >= 3)
                or (rank >= 70 and vol_ratio >= 1.8 and rank_slope > 1)
            ):
                phase = "IGNITION"
                strat = "ESE"

            # ACCUMULATION: 高ランク + 低ボラ + ピボット圏内（最注目）
            elif rank >= 80 and abs(rank_slope) < 2 and 0.0 <= dist <= 0.08:
                phase = "ACCUMULATION"
                strat = "PBVH"

            elif rank >= 65:
                phase = "HOLD/WATCH"

            return ECRStrategyEngine._compile_result(ticker, curr, dyn, phase, strat)

        except Exception:
            return ECRStrategyEngine._empty_result(ticker)

    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _calculate_metrics(df: pd.DataFrame) -> dict:
        try:
            vcp_res = VCPAnalyzer.calculate(df)
            ses_res = SentinelEfficiencyAnalyzer.calculate(df)
            rs_raw  = RSAnalyzer.get_raw_score(df)

            vcp = vcp_res.get("score", 0)
            ses = ses_res.get("score", 0)

            # RS を 0-100 にスケーリング（-1〜+1 → 0〜100）
            rs_score = int(np.clip((rs_raw + 0.3) * 100, 0, 100)) if rs_raw != -999.0 else 0

            # ピボット距離（直近50日高値から現在値）
            price = float(df["Close"].iloc[-1])
            pivot = float(df["High"].iloc[-50:].max())
            dist  = (pivot - price) / pivot  # 正 = まだ届いていない, 負 = 突破済み

            # 出来高比（直近1日 vs 20日平均）
            v_now = float(df["Volume"].iloc[-1])
            v_avg = float(df["Volume"].iloc[-20:].mean())
            vol_ratio = round(v_now / v_avg, 2) if v_avg > 0 else 1.0

            # Rank（重み付け合成 + ボーナス）
            raw_rank = vcp * 0.40 + ses * 0.30 + rs_score * 0.30
            if   vcp >= 95 and ses >= 80: raw_rank *= 1.15
            elif vcp >= 85 and ses >= 70: raw_rank *= 1.05

            return {
                "rank":          int(min(100, raw_rank)),
                "vcp":           vcp,
                "ses":           ses,
                "rs":            rs_score,
                "dist_to_pivot": round(dist, 4),
                "vol_ratio":     vol_ratio,
            }
        except Exception:
            return {"rank": 0, "vcp": 0, "ses": 0, "rs": 0,
                    "dist_to_pivot": 0.0, "vol_ratio": 1.0}

    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _compile_result(ticker: str, curr: dict, dyn: dict,
                        phase: str, strat: str) -> dict:
        return {
            "ticker":        ticker,
            "sentinel_rank": curr["rank"],
            "phase":         phase,
            "strategy":      strat,
            "dynamics":      dyn,
            "components": {
                "energy_vcp":   curr["vcp"],
                "quality_ses":  curr["ses"],
                "momentum_rs":  curr["rs"],
            },
            "metrics": {
                "dist_to_pivot_pct": round(curr["dist_to_pivot"] * 100, 2),
                "volume_ratio":      curr["vol_ratio"],
            },
        }

    @staticmethod
    def _empty_result(ticker: str) -> dict:
        return {
            "ticker": ticker, "sentinel_rank": 0,
            "phase": "ERR", "strategy": "NONE",
            "dynamics":   {"rank_delta": 0, "rank_5d_slope": 0, "vol_change_ratio": 0},
            "components": {"energy_vcp": 0, "quality_ses": 0, "momentum_rs": 0},
            "metrics":    {"dist_to_pivot_pct": 0, "volume_ratio": 0},
        }
