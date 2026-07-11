import pandas as pd
import numpy as np
from .config import CONFIG


class VCPAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 130:
                return VCPAnalyzer._empty()
            close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low  - close.shift()).abs()
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])

            periods = [20, 30, 40, 60]
            ranges  = []
            for p in periods:
                h, l = float(high.iloc[-p:].max()), float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            avg_range      = float(np.mean(ranges[:3]))
            is_contracting = ranges[0] < ranges[1] < ranges[2]

            tight_score = (
                40 if avg_range < 0.10 else
                30 if avg_range < 0.15 else
                20 if avg_range < 0.20 else
                10 if avg_range < 0.28 else 0
            )
            if is_contracting:
                tight_score += 5
            tight_score = min(40, tight_score)

            v20_avg = float(volume.iloc[-20:].mean())
            v60_avg = float(volume.iloc[-60:-40].mean())
            v_ratio = v20_avg / v60_avg if v60_avg > 0 else 1.0
            vol_score = (
                30 if v_ratio < 0.45 else
                25 if v_ratio < 0.60 else
                15 if v_ratio < 0.75 else 0
            )

            ma50  = float(close.rolling(50).mean().iloc[-1])
            ma150 = float(close.rolling(150).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])
            ma_score = (
                (10 if price > ma50  else 0) +
                (10 if ma50  > ma150 else 0) +
                (10 if ma150 > ma200 else 0)
            )

            pivot    = float(high.iloc[-50:].max())
            distance = (pivot - price) / pivot
            pivot_bonus = (
                5 if 0    <= distance <= 0.04 else
                3 if 0.04 <  distance <= 0.08 else 0
            )

            signals = []
            if tight_score >= 35:  signals.append("Tight Base (VCP)")
            if is_contracting:     signals.append("V-Contraction Detected")
            if v_ratio < 0.75:     signals.append("Volume Dry-up Detected")
            if ma_score >= 20:     signals.append("Trend Alignment OK")
            if pivot_bonus > 0:    signals.append("Near Pivot Point")

            return {
                "score":     int(min(105, tight_score + vol_score + ma_score + pivot_bonus)),
                "atr":       atr,
                "signals":   signals,
                "is_dryup":  v_ratio < 0.75,
                "range_pct": round(ranges[0], 4),
                "vol_ratio": round(v_ratio, 2),
                "breakdown": {
                    "tight": tight_score,
                    "vol":   vol_score,
                    "ma":    ma_score,
                    "pivot": pivot_bonus,
                },
            }
        except Exception:
            return VCPAnalyzer._empty()

    @staticmethod
    def _empty() -> dict:
        return {
            "score": 0, "atr": 0.0, "signals": [],
            "is_dryup": False, "range_pct": 0.0, "vol_ratio": 1.0,
            "breakdown": {"tight": 0, "vol": 0, "ma": 0, "pivot": 0},
        }


class RSAnalyzer:
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 21:
                return -999.0
            r = lambda n: (c.iloc[-1] / c.iloc[-n] - 1) if len(c) >= n else (c.iloc[-1] / c.iloc[0] - 1)
            return (r(252) * 0.4) + (r(126) * 0.2) + (r(63) * 0.2) + (r(21) * 0.2)
        except Exception:
            return -999.0

    @staticmethod
    def assign_percentiles(raw_list: list) -> list:
        if not raw_list:
            return []
        raw_list.sort(key=lambda x: x["raw_rs"])
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 99) + 1
        return raw_list


class StrategyValidator:
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 200:
                return 1.0
            close, high, low = df["Close"], df["High"], df["Low"]
            tr  = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low  - close.shift()).abs()
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            trades, in_pos, entry_p, stop_p = [], False, 0.0, 0.0
            for i in range(max(50, len(df) - 250), len(df)):
                if in_pos:
                    if low.iloc[i] <= stop_p:
                        trades.append(-1.0); in_pos = False
                    elif high.iloc[i] >= entry_p + (entry_p - stop_p) * CONFIG["TARGET_R_MULTIPLE"]:
                        trades.append(CONFIG["TARGET_R_MULTIPLE"]); in_pos = False
                    elif i == len(df) - 1:
                        trades.append(
                            (close.iloc[i] - entry_p) / (entry_p - stop_p)
                            if entry_p > stop_p else 0
                        ); in_pos = False
                else:
                    pivot = high.iloc[i - 20:i].max()
                    if close.iloc[i] > pivot and close.iloc[i] > close.rolling(50).mean().iloc[i]:
                        in_pos  = True
                        entry_p = float(close.iloc[i])
                        stop_p  = entry_p - float(atr.iloc[i]) * CONFIG["STOP_LOSS_ATR"]

            if not trades:
                return 1.0
            pos = sum(t for t in trades if t > 0)
            neg = abs(sum(t for t in trades if t < 0))
            return round(min(10.0, pos / neg if neg > 0 else (5.0 if pos > 0 else 1.0)), 2)
        except Exception:
            return 1.0
