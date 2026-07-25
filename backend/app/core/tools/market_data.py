import json
import yfinance as yf
from app.core.tools.registry import tool_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)

@tool_registry.register(name="get_stock_quote", description="Fetches accurate real-time and historical stock quotes, dividend yields, and market data using Yahoo Finance. Use this instead of web search to avoid hallucinating prices. Ticker examples: HDV, AAPL, 7203.T.")
def get_stock_quote(ticker: str) -> str:
    """
    Fetches accurate real-time and historical stock quotes, dividend yields, and market data using Yahoo Finance.
    Use this instead of web search to avoid hallucinating prices.
    Ticker examples: HDV, AAPL, 7203.T.
    """
    logger.info(f"Fetching stock quote for {ticker}")
    
    # 指数の名前揺れを吸収するマッピング
    ticker_upper = ticker.upper().strip()
    if ticker_upper in ["S&P 500", "S&P500", "SPX"]:
        ticker = "^GSPC"
    elif ticker_upper in ["DOW", "DOW JONES", "DJI", "NY DOW"]:
        ticker = "^DJI"
    elif ticker_upper in ["NASDAQ", "COMP"]:
        ticker = "^IXIC"
    elif ticker_upper in ["NIKKEI", "NIKKEI 225", "NIKKEI225", "N225"]:
        ticker = "^N225"
    elif ticker_upper in ["SOX", "PHLX"]:
        ticker = "^SOX"

    try:
        t = yf.Ticker(ticker)
        info = t.info
        history = t.history(period="5d")
        
        current_price = None
        previous_close = None
        if not history.empty:
            current_price = float(history['Close'].iloc[-1])
            if len(history) > 1:
                previous_close = float(history['Close'].iloc[-2])
                
        # Determine the current price fallback if history fails
        if current_price is None:
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if previous_close is None:
            previous_close = info.get("previousClose")

        # Determine dividend yield
        dividend_yield = info.get("dividendYield")
        if dividend_yield is not None:
            val = dividend_yield * 100 if dividend_yield < 1 else dividend_yield
            dividend_yield = f"{val:.2f}%"
        else:
            dividend_yield = info.get("yield")
            if dividend_yield is not None:
                val = dividend_yield * 100 if dividend_yield < 1 else dividend_yield
                dividend_yield = f"{val:.2f}%"

        result = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "current_price": current_price,
            "previous_close": previous_close,
            "open": info.get("open"),
            "day_low": info.get("dayLow"),
            "day_high": info.get("dayHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "volume": info.get("volume"),
            "dividend_yield": dividend_yield,
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "USD"),
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error fetching stock quote for {ticker}: {e}")
        return json.dumps({"error": f"Failed to fetch data for {ticker}. Exception: {e}"})
