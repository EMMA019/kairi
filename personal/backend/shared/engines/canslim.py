"""
canslim.py
==========
CANSLIM 簡易版スコアリングエンジン（William O'Neil 手法）

実装要素:
  C — Current Earnings     : EPS成長率（YoY）      25pt
  A — Annual Sales Growth  : 売上成長率（YoY）      20pt
  N — New 52w High         : 52週高値近接            20pt
  S — Supply/Demand (Vol)  : 出来高急増 + 株価上昇   20pt
  L — Leader or Laggard    : RS Rating 上位          15pt
  I — Institutional Buying : Starterプラン非対応 → 0固定

※ income-statement から C/A を自前計算
※ fund引数がNoneの場合はFMPから直接取得
"""
import pandas as pd
import numpy as np

try:
    from .analysis import RSAnalyzer
    from engines import core_fmp
except ImportError:
    from analysis import RSAnalyzer
    import core_fmp


class CANSLIMAnalyzer:

    @staticmethod
    def _fetch_income_statements(ticker: str) -> list:
        """
        /stable/income-statement から年次データを3期分取得。
        24時間キャッシュ済み。
        """
        data = core_fmp._get(
            f"{core_fmp.BASE_URL}/income-statement",
            {"symbol": ticker, "period": "annual", "limit": 3},
            cache_key=f"incstmt_{ticker}",
            ttl=24 * 3600,
        )
        return data if isinstance(data, list) else []

    @staticmethod
    def calculate(ticker: str, df: pd.DataFrame,
                  fund: dict | None = None,
                  own:  dict | None = None) -> dict:
        """
        Parameters
        ----------
        ticker : str
        df     : OHLCV DataFrame（100日以上）
        fund   : core_fmp.get_fundamentals() の結果（省略可）
        own    : core_fmp.get_ownership() の結果（省略可・Starter非対応）
        """
        try:
            if df is None or len(df) < 100:
                return CANSLIMAnalyzer._empty(ticker)

            close  = df["Close"]
            volume = df["Volume"]
            price  = float(close.iloc[-1])

            # ── income-statement 取得（C/A の計算に使用） ──────────
            stmts = CANSLIMAnalyzer._fetch_income_statements(ticker)

            # ── C: Current Earnings — EPS成長率 (25pt) ────────────
            c_score    = 0
            eps_growth = None

            if len(stmts) >= 2:
                eps_curr = stmts[0].get("eps") or stmts[0].get("epsDiluted")
                eps_prev = stmts[1].get("eps") or stmts[1].get("epsDiluted")
                if eps_curr is not None and eps_prev is not None:
                    eps_curr = float(eps_curr)
                    eps_prev = float(eps_prev)
                    if eps_prev > 0:
                        eps_growth = (eps_curr - eps_prev) / eps_prev * 100
                        c_score = (
                            25 if eps_growth >= 50 else
                            20 if eps_growth >= 30 else
                            15 if eps_growth >= 20 else
                            10 if eps_growth >= 10 else
                             5 if eps_growth >=  0 else 0
                        )
            elif fund:
                # フォールバック: fund から取得
                eg = fund.get("earnings_growth_yoy")
                if eg is not None:
                    eps_growth = float(eg)
                    c_score = (
                        25 if eps_growth >= 50 else
                        20 if eps_growth >= 30 else
                        15 if eps_growth >= 20 else
                        10 if eps_growth >= 10 else
                         5 if eps_growth >=  0 else 0
                    )

            # ── A: Annual Sales Growth — 売上成長率 (20pt) ────────
            a_score    = 0
            rev_growth = None

            if len(stmts) >= 2:
                rev_curr = stmts[0].get("revenue")
                rev_prev = stmts[1].get("revenue")
                if rev_curr is not None and rev_prev is not None:
                    rev_curr = float(rev_curr)
                    rev_prev = float(rev_prev)
                    if rev_prev > 0:
                        rev_growth = (rev_curr - rev_prev) / rev_prev * 100
                        a_score = (
                            20 if rev_growth >= 30 else
                            15 if rev_growth >= 20 else
                            10 if rev_growth >= 10 else
                             5 if rev_growth >=  5 else 0
                        )
            elif fund:
                rg = fund.get("revenue_growth_yoy")
                if rg is not None:
                    rev_growth = float(rg)
                    a_score = (
                        20 if rev_growth >= 30 else
                        15 if rev_growth >= 20 else
                        10 if rev_growth >= 10 else
                         5 if rev_growth >=  5 else 0
                    )

            # ── N: New 52-week High Proximity (20pt) ──────────────
            n_score   = 0
            high_52w  = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
            dist_from_high = (high_52w - price) / high_52w
            n_score = (
                20 if dist_from_high <= 0.03 else
                15 if dist_from_high <= 0.07 else
                10 if dist_from_high <= 0.12 else
                 5 if dist_from_high <= 0.20 else 0
            )

            # ── S: Supply/Demand — 出来高 × 価格変動 (20pt) ───────
            s_score    = 0
            price_chg  = close.pct_change()
            vol_20     = volume.iloc[-20:]
            prc_20     = price_chg.iloc[-20:]
            vol_avg    = float(volume.iloc[-50:-20].mean()) if len(volume) >= 50 else float(vol_20.mean())

            up_vol_days   = int(((vol_20 > vol_avg * 1.2) & (prc_20 > 0)).sum())
            down_vol_days = int(((vol_20 > vol_avg * 1.2) & (prc_20 < 0)).sum())
            net_demand    = up_vol_days - down_vol_days

            s_score = (
                20 if net_demand >= 4 else
                15 if net_demand >= 2 else
                10 if net_demand >= 0 else
                 0 if net_demand >= -1 else -5
            )

            # ── L: Leader — RS Rating (15pt) ──────────────────────
            l_score = 0
            rs_raw  = RSAnalyzer.get_raw_score(df)
            rs_pct  = int(np.clip((rs_raw + 0.3) * 100, 0, 100)) if rs_raw != -999.0 else 0
            l_score = (
                15 if rs_pct >= 90 else
                10 if rs_pct >= 80 else
                 5 if rs_pct >= 70 else 0
            )

            # ── I: Institutional — Starter非対応 → 0固定 ──────────
            i_score = 0

            # ── 集計 ───────────────────────────────────────────────
            total = c_score + a_score + n_score + s_score + l_score + i_score
            total = int(max(0, min(100, total)))

            grade = (
                "A+" if total >= 80 else
                "A"  if total >= 70 else
                "B+" if total >= 60 else
                "B"  if total >= 50 else
                "C"  if total >= 35 else "D"
            )

            return {
                "ticker": ticker,
                "score":  total,
                "grade":  grade,
                "breakdown": {
                    "C_earnings":  c_score,
                    "A_sales":     a_score,
                    "N_new_high":  n_score,
                    "S_volume":    s_score,
                    "L_rs_leader": l_score,
                    "I_inst":      i_score,
                },
                "metrics": {
                    "eps_growth":        eps_growth,
                    "rev_growth":        rev_growth,
                    "dist_from_52w_pct": round(dist_from_high * 100, 1),
                    "net_demand_days":   net_demand,
                    "rs_pct":            rs_pct,
                },
            }

        except Exception as e:
            return CANSLIMAnalyzer._empty(ticker)

    @staticmethod
    def _empty(ticker: str) -> dict:
        return {
            "ticker": ticker, "score": 0, "grade": "D",
            "breakdown": {
                "C_earnings": 0, "A_sales": 0, "N_new_high": 0,
                "S_volume": 0, "L_rs_leader": 0, "I_inst": 0,
            },
            "metrics": {
                "eps_growth": None, "rev_growth": None,
                "dist_from_52w_pct": None, "net_demand_days": 0, "rs_pct": 0,
            },
        }
