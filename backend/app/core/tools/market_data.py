import json
from typing import Any, Optional

import yfinance as yf
from app.core.tools.registry import tool_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 日本市況スナップショット用ティッカー
JP_INDEX_TICKERS = {
    "^N225": "日経平均",
    "^TOPX": "TOPIX",
}
JP_SECTOR_ETFS = {
    "1631.T": "銀行業ETF",
    "1632.T": "金融業ETF",
    "1625.T": "電機・精密ETF",
    "1621.T": "医薬品ETF",
}


def _normalize_ticker(ticker: str) -> str:
    ticker_upper = ticker.upper().strip()
    if ticker_upper in ["S&P 500", "S&P500", "SPX"]:
        return "^GSPC"
    if ticker_upper in ["DOW", "DOW JONES", "DJI", "NY DOW"]:
        return "^DJI"
    if ticker_upper in ["NASDAQ", "COMP"]:
        return "^IXIC"
    if ticker_upper in ["NIKKEI", "NIKKEI 225", "NIKKEI225", "N225", "^N225"]:
        return "^N225"
    if ticker_upper in ["TOPIX", "^TOPX", "TPX", "トピックス"]:
        return "^TOPX"
    if ticker_upper in ["SOX", "PHLX"]:
        return "^SOX"
    return ticker


def _quote_dict(ticker: str) -> dict[str, Any]:
    ticker = _normalize_ticker(ticker)
    t = yf.Ticker(ticker)
    info = t.info or {}
    history = t.history(period="5d")

    current_price = None
    previous_close = None
    day_open = None
    day_high = None
    day_low = None
    if history is not None and not history.empty:
        current_price = float(history["Close"].iloc[-1])
        if len(history) > 1:
            previous_close = float(history["Close"].iloc[-2])
        day_open = float(history["Open"].iloc[-1]) if "Open" in history.columns else None
        day_high = float(history["High"].iloc[-1]) if "High" in history.columns else None
        day_low = float(history["Low"].iloc[-1]) if "Low" in history.columns else None

    if current_price is None:
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if previous_close is None:
        previous_close = info.get("previousClose")

    change = None
    change_pct = None
    if current_price is not None and previous_close not in (None, 0):
        change = current_price - previous_close
        change_pct = (change / previous_close) * 100.0

    dividend_yield = info.get("dividendYield")
    if dividend_yield is not None:
        val = dividend_yield * 100 if dividend_yield < 1 else dividend_yield
        dividend_yield = f"{val:.2f}%"
    else:
        yld = info.get("yield")
        if yld is not None:
            val = yld * 100 if yld < 1 else yld
            dividend_yield = f"{val:.2f}%"
        else:
            dividend_yield = None

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "current_price": current_price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "open": day_open if day_open is not None else info.get("open"),
        "day_low": day_low if day_low is not None else info.get("dayLow"),
        "day_high": day_high if day_high is not None else info.get("dayHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "volume": info.get("volume"),
        "dividend_yield": dividend_yield,
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "currency": info.get("currency", "USD"),
    }


@tool_registry.register(
    name="get_stock_quote",
    description=(
        "Fetches accurate real-time and historical stock quotes, dividend yields, and market data "
        "using Yahoo Finance. Use this instead of web search to avoid hallucinating prices. "
        "Ticker examples: HDV, AAPL, 7203.T, ^N225, TOPIX."
    ),
)
def get_stock_quote(ticker: str) -> str:
    logger.info(f"Fetching stock quote for {ticker}")
    try:
        result = _quote_dict(ticker)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error fetching stock quote for {ticker}: {e}")
        return json.dumps({"error": f"Failed to fetch data for {ticker}. Exception: {e}"})


def get_jp_market_snapshot(include_sectors: bool = True) -> dict[str, Any]:
    """
    日経・TOPIX・主要業種ETFの終値と前日比をまとめて返す。
    """
    out: dict[str, Any] = {"indices": {}, "sectors": {}, "errors": []}
    for ticker, label in JP_INDEX_TICKERS.items():
        try:
            q = _quote_dict(ticker)
            q["label"] = label
            out["indices"][ticker] = q
        except Exception as e:
            out["errors"].append(f"{ticker}: {e}")
            logger.warning(f"JP index snapshot failed {ticker}: {e}")

    if include_sectors:
        for ticker, label in JP_SECTOR_ETFS.items():
            try:
                q = _quote_dict(ticker)
                q["label"] = label
                out["sectors"][ticker] = q
            except Exception as e:
                out["errors"].append(f"{ticker}: {e}")
                logger.warning(f"JP sector snapshot failed {ticker}: {e}")
    return out


@tool_registry.register(
    name="get_jp_market_snapshot",
    description=(
        "日本市場の日経平均・TOPIX・主要業種ETF（銀行/金融/電機/医薬）の終値と前日比を一括取得。"
        "今日の日本市場・TOPIX・金融セクターの質問で優先使用。"
    ),
)
def get_jp_market_snapshot_tool() -> str:
    try:
        return json.dumps(get_jp_market_snapshot(include_sectors=True), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _fmt_pct(q: dict[str, Any]) -> str:
    price = q.get("current_price")
    chg = q.get("change")
    pct = q.get("change_pct")
    if price is None:
        return "取得失敗"
    parts = [f"{price:,.2f}" if isinstance(price, (int, float)) else str(price)]
    if chg is not None and pct is not None:
        sign = "+" if chg >= 0 else ""
        parts.append(f"{sign}{chg:,.2f}（{sign}{pct:.2f}%）")
    return " ".join(parts)


def format_jp_market_snapshot_for_prompt(user_input: str = "") -> str:
    """
    検索結果先頭に注入する確定数値ブロック。
    推測埋め禁止の注意書き付き。
    """
    snap = get_jp_market_snapshot(include_sectors=True)
    lines = [
        "【Yahoo Finance 確定スナップショット（推測禁止・この数値を優先）】",
        "※ TOPIX・業種別騰落がここに無い／取得失敗の場合は推測で埋めず『未確認』と書くこと。",
    ]
    for ticker, q in (snap.get("indices") or {}).items():
        label = q.get("label") or ticker
        lines.append(f"- {label} ({ticker}): {_fmt_pct(q)}")
    lines.append("主要業種ETF（参考・東証業種代理）:")
    for ticker, q in (snap.get("sectors") or {}).items():
        label = q.get("label") or ticker
        lines.append(f"- {label} ({ticker}): {_fmt_pct(q)}")
    errs = snap.get("errors") or []
    if errs:
        lines.append("取得エラー: " + "; ".join(errs[:5]))
    return "\n".join(lines) + "\n"
