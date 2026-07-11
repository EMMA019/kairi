"""
core_polygon.py — Polygon.io API Client (無料プラン対応)
全米株のヒストリカルデータ（日足）を取得する。
無料プラン：1分間5リクエスト、1日500リクエスト
"""
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import hashlib
import json

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
BASE_URL = "https://api.polygon.io"

CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get(url: str, params: dict = None, cache_key: str = None, ttl: int = 3600):
    """キャッシュ付きGET（レート制限対応）"""
    params = params or {}
    params["apiKey"] = POLYGON_API_KEY

    if cache_key:
        h = hashlib.md5(cache_key.encode()).hexdigest()
        cache_file = CACHE_DIR / f"{h}.json"
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime < ttl):
            try:
                return json.loads(cache_file.read_text())
            except:
                pass

    time.sleep(0.3)  # レート制限対策（1分5req → 12秒に1回）

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 429:
            print("⚠️ Rate limit exceeded (429). Waiting 60s...")
            time.sleep(60)
            return _get(url, params, cache_key, ttl)
        resp.raise_for_status()
        data = resp.json()
        if cache_key and data:
            cache_file.write_text(json.dumps(data))
        return data
    except Exception as e:
        print(f"Polygon API error: {e}")
        return None


def get_historical_data(ticker: str, days: int = 200) -> pd.DataFrame | None:
    """
    Polygon.io から日足データを取得（無料プラン対応）
    - 全米株（NYSE/NASDAQ）全ティッカー対応
    - 無料プラン：過去2年分のデータが取得可能
    """
    if not POLYGON_API_KEY:
        print("⚠️ POLYGON_API_KEY が設定されていません。")
        return None

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")

    cache_key = f"polygon_hist_{ticker}_{start_date}_{end_date}"
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"

    data = _get(url, cache_key=cache_key, ttl=12 * 3600)
    if not data or "results" not in data:
        return None

    results = data["results"]
    if not results:
        return None

    df = pd.DataFrame(results)
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.tz_localize(None)
    df = df.set_index("date").sort_index()

    df = df.rename(columns={
        "o": "Open",
        "h": "High",
        "l": "Low",
        "c": "Close",
        "v": "Volume"
    })

    df = df[["Open", "High", "Low", "Close", "Volume"]]

    if len(df) > days:
        df = df.iloc[-days:]

    return df


def get_previous_close(ticker: str) -> dict | None:
    """
    前営業日の終値データを取得（スキャナー用）
    """
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/prev"
    data = _get(url, cache_key=f"polygon_prev_{ticker}", ttl=6 * 3600)

    if not data or "results" not in data:
        return None

    results = data["results"]
    if not results:
        return None

    return {
        "ticker": ticker,
        "close": results[0]["c"],
        "volume": results[0]["v"],
        "high": results[0]["h"],
        "low": results[0]["l"],
        "open": results[0]["o"],
        "timestamp": results[0]["t"]
    }


def get_bulk_previous_close(tickers: list) -> dict:
    """
    複数銘柄の前営業日終値を一括取得（バッチ処理用）
    無料プランでは1回のリクエストで全銘柄を取得するのは不可 → ループで回す
    """
    results = {}
    for ticker in tickers:
        data = get_previous_close(ticker)
        if data:
            results[ticker] = data
        # レート制限対策のスリープは _get 内で実施済み
    return results