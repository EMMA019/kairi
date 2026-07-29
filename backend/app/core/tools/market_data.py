import json
from typing import Any

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
    if ticker_upper in ["USDJPY", "USD/JPY", "USD.JPY", "USDJPY=X"]:
        return "USDJPY=X"
    return ticker


def _atr14_from_history(history: Any) -> float | None:
    """簡易 ATR(14)。High/Low/Close が必要。"""
    try:
        if history is None or getattr(history, "empty", True) or len(history) < 15:
            return None
        if not all(c in history.columns for c in ("High", "Low", "Close")):
            return None
        high = history["High"].astype(float)
        low = history["Low"].astype(float)
        close = history["Close"].astype(float)
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = tr1.combine(tr2, max).combine(tr3, max)
        atr = float(tr.iloc[-14:].mean())
        if atr != atr:  # NaN
            return None
        return atr
    except Exception:
        return None


def _vol_atr_metrics(ticker: str) -> dict[str, Any]:
    """出来高・平均出来高・ATR・日中レンジ用メトリクス（主に yfinance history）。"""
    ticker = _normalize_ticker(ticker)
    out: dict[str, Any] = {
        "volume": None,
        "average_volume": None,
        "atr": None,
        "day_range": None,
    }
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        history = t.history(period="1mo")
        vol = info.get("volume") or info.get("regularMarketVolume")
        avg_vol = info.get("averageVolume") or info.get("averageVolume10days")
        if history is not None and not history.empty:
            if "Volume" in history.columns:
                last_vol = float(history["Volume"].iloc[-1])
                if vol is None:
                    vol = last_vol
                if avg_vol is None and len(history) >= 5:
                    avg_vol = float(history["Volume"].tail(20).mean())
            day_high = float(history["High"].iloc[-1]) if "High" in history.columns else None
            day_low = float(history["Low"].iloc[-1]) if "Low" in history.columns else None
            if day_high is not None and day_low is not None:
                out["day_range"] = day_high - day_low
                out["day_high"] = day_high
                out["day_low"] = day_low
            out["atr"] = _atr14_from_history(history)
        out["volume"] = float(vol) if vol is not None else None
        out["average_volume"] = float(avg_vol) if avg_vol is not None else None
        if out["volume"] is not None and out["average_volume"] not in (None, 0):
            out["volume_ratio"] = out["volume"] / out["average_volume"]
        else:
            out["volume_ratio"] = None
    except Exception as e:
        logger.warning(f"vol/ATR metrics failed {ticker}: {e}")
    return out


def _merge_vol_atr(quote: dict[str, Any]) -> dict[str, Any]:
    """既存 quote に volume / average_volume / atr / volume_ratio を足す。"""
    q = dict(quote)
    ticker = str(q.get("ticker") or "")
    m = _vol_atr_metrics(ticker)
    if q.get("volume") is None and m.get("volume") is not None:
        q["volume"] = m["volume"]
    if q.get("day_high") is None and m.get("day_high") is not None:
        q["day_high"] = m["day_high"]
    if q.get("day_low") is None and m.get("day_low") is not None:
        q["day_low"] = m["day_low"]
    q["average_volume"] = m.get("average_volume")
    q["atr"] = m.get("atr")
    q["day_range"] = m.get("day_range")
    if q.get("volume") is not None and q.get("average_volume") not in (None, 0):
        try:
            q["volume_ratio"] = float(q["volume"]) / float(q["average_volume"])
        except (TypeError, ValueError, ZeroDivisionError):
            q["volume_ratio"] = m.get("volume_ratio")
    else:
        q["volume_ratio"] = m.get("volume_ratio")
    return q


def _format_dividend_yield(
    info: dict[str, Any],
    current_price: float | None,
    previous_close: float | None,
) -> str | None:
    """
    yfinance の dividendYield は時期によって「比率(0.004=0.4%)」と
    「すでに%近傍(0.32=0.32%)」が混在する。AAPL で 0.32→×100=32% になる事故を防ぐ。

    優先: annual dividendRate / price から算出。
    """
    price = current_price or previous_close or info.get("currentPrice") or info.get("regularMarketPrice")
    div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
    try:
        if div_rate is not None and price not in (None, 0):
            pct = (float(div_rate) / float(price)) * 100.0
            if 0 <= pct < 100:
                return f"{pct:.2f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    raw = info.get("dividendYield")
    if raw is None:
        raw = info.get("trailingAnnualDividendYield")
    if raw is None:
        raw = info.get("yield")
    if raw is None:
        return None
    try:
        dy = float(raw)
    except (TypeError, ValueError):
        return None

    if dy >= 1:
        pct = dy
    elif dy > 0.05:
        pct = dy
    else:
        pct = dy * 100.0
    if pct < 0 or pct >= 100:
        return None
    return f"{pct:.2f}%"


def _quote_dict_yf(ticker: str) -> dict[str, Any]:
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

    dividend_yield = _format_dividend_yield(info, current_price, previous_close)

    # 5d だけでは ATR14 不足なのでメトリクスは別途 1mo
    metrics = _vol_atr_metrics(ticker)
    volume = info.get("volume") or info.get("regularMarketVolume") or metrics.get("volume")
    avg_vol = metrics.get("average_volume")
    atr = metrics.get("atr")
    day_range = None
    dh = day_high if day_high is not None else info.get("dayHigh")
    dl = day_low if day_low is not None else info.get("dayLow")
    if dh is not None and dl is not None:
        try:
            day_range = float(dh) - float(dl)
        except (TypeError, ValueError):
            day_range = metrics.get("day_range")
    else:
        day_range = metrics.get("day_range")
    volume_ratio = None
    if volume is not None and avg_vol not in (None, 0):
        try:
            volume_ratio = float(volume) / float(avg_vol)
        except (TypeError, ValueError, ZeroDivisionError):
            volume_ratio = None

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "current_price": current_price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "open": day_open if day_open is not None else info.get("open"),
        "day_low": dl,
        "day_high": dh,
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "volume": volume,
        "average_volume": avg_vol,
        "volume_ratio": volume_ratio,
        "atr": atr,
        "day_range": day_range,
        "dividend_yield": dividend_yield,
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "currency": info.get("currency", "USD"),
        "source": "yfinance",
    }


def _try_ibkr_quote(ticker: str) -> dict[str, Any] | None:
    try:
        from app.core.ibkr.client import fetch_quote, ibkr_market_data_enabled

        if not ibkr_market_data_enabled():
            return None
        payload = fetch_quote(_normalize_ticker(ticker))
        if not payload.get("ok"):
            logger.info(f"IBKR quote miss {ticker}: {payload.get('error')} {payload.get('message')}")
            return None
        data = payload.get("data") or {}
        if data.get("current_price") is None:
            return None
        return data
    except Exception as e:
        logger.warning(f"IBKR quote path error {ticker}: {e}")
        return None


def _quote_dict(ticker: str) -> dict[str, Any]:
    """IBKR 優先、失敗時 yfinance。volume/ATR は不足分を補完。"""
    ib = _try_ibkr_quote(ticker)
    if ib is not None:
        return _merge_vol_atr(ib)
    return _quote_dict_yf(ticker)


@tool_registry.register(
    name="get_stock_quote",
    description=(
        "Fetches stock quotes (IBKR preferred when TWS connected, else Yahoo Finance). "
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
    IBKR バッチ優先、欠けた銘柄は yfinance。
    """
    out: dict[str, Any] = {"indices": {}, "sectors": {}, "errors": [], "source": "mixed"}
    symbols = list(JP_INDEX_TICKERS.keys())
    if include_sectors:
        symbols.extend(JP_SECTOR_ETFS.keys())

    ib_quotes: dict[str, Any] = {}
    try:
        from app.core.ibkr.client import fetch_quotes, ibkr_market_data_enabled

        if ibkr_market_data_enabled():
            payload = fetch_quotes(symbols)
            if payload.get("ok"):
                ib_quotes = (payload.get("data") or {}).get("quotes") or {}
                out["source"] = "ibkr"
            else:
                out["errors"].append(f"ibkr_batch: {payload.get('error')} {payload.get('message')}")
    except Exception as e:
        out["errors"].append(f"ibkr_batch: {e}")
        logger.warning(f"JP snapshot IBKR batch failed: {e}")

    sources_used = set()

    def _fill(bucket: str, mapping: dict[str, str]) -> None:
        for ticker, label in mapping.items():
            q = ib_quotes.get(ticker)
            if q and not q.get("error") and q.get("current_price") is not None:
                q = dict(q)
                q["label"] = label
                out[bucket][ticker] = q
                sources_used.add(q.get("source") or "ibkr")
                continue
            try:
                yq = _quote_dict_yf(ticker)
                yq["label"] = label
                out[bucket][ticker] = yq
                sources_used.add("yfinance")
                if q and q.get("error"):
                    out["errors"].append(f"{ticker}: ibkr={q.get('message')}; used yfinance")
            except Exception as e:
                out["errors"].append(f"{ticker}: {e}")
                logger.warning(f"JP snapshot failed {ticker}: {e}")

    _fill("indices", JP_INDEX_TICKERS)
    if include_sectors:
        _fill("sectors", JP_SECTOR_ETFS)

    if sources_used == {"ibkr"}:
        out["source"] = "ibkr"
    elif sources_used == {"yfinance"}:
        out["source"] = "yfinance"
    else:
        out["source"] = "mixed"
    return out


@tool_registry.register(
    name="get_jp_market_snapshot",
    description=(
        "日本市場の日経平均・TOPIX・主要業種ETF（銀行/金融/電機/医薬）の終値と前日比を一括取得。"
        "IBKR 優先（TWS 接続時）、不足分は Yahoo。今日の日本市場・TOPIX・金融セクターの質問で優先使用。"
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
    src = snap.get("source") or "mixed"
    lines = [
        f"【市場スナップショット source={src}（推測禁止・この数値を優先）】",
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
