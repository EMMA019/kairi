#!/usr/bin/env python3
"""
backend/main.py — SENTINEL PERSONAL バックエンド統合サーバー
============================================================
全機能:
- POST /api/generate-strategies  全銘柄スキャン実行
- POST /api/generate-articles    日次レポート生成
- POST /api/ai-judge             AI判断実行
- POST /api/scrape-news          ニュース収集
- GET  /api/quote/{ticker}       リアルタイム株価取得（FMP直接）
- GET  /api/historical/{ticker}  過去株価取得（FMP直接）
- GET  /api/status               システム状態確認
- GET  /api/logs                 実行ログ取得

起動:
  uvicorn backend.main:app --reload --port 8000
"""
import os, sys, json, subprocess, traceback, asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import queue
import requests

# プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "shared"))

# FMP API設定
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

app = FastAPI(title="Sentinel Personal API", version="1.0.0")

# CORS設定（フロントエンドからのリクエスト許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番では具体的なドメイン指定推奨
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ログキュー（最新100件保持）
log_queue = queue.Queue(maxsize=100)

def add_log(level: str, message: str):
    """ログ追加"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message
    }
    try:
        log_queue.put_nowait(entry)
    except queue.Full:
        log_queue.get()  # 古いログを削除
        log_queue.put(entry)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FMP API 直接呼び出し
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fmp_get(endpoint: str, params: dict = None) -> dict:
    """FMP API GET リクエスト"""
    params = params or {}
    params["apikey"] = FMP_API_KEY
    
    try:
        url = f"{FMP_BASE_URL}/{endpoint}"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        add_log("ERROR", f"FMP API error: {e}")
        raise HTTPException(status_code=502, detail=f"FMP API error: {str(e)}")
    except Exception as e:
        add_log("ERROR", f"Request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# リクエストモデル
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AIJudgeRequest(BaseModel):
    ticker: str

class NewsRequest(BaseModel):
    ticker: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ヘルパー関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_script(script_path: str, args: list = None, env: dict = None) -> dict:
    """Pythonスクリプト実行"""
    args = args or []
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    
    cmd = [sys.executable, str(script_path)] + args
    
    try:
        add_log("INFO", f"実行開始: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env_vars,
            capture_output=True,
            text=True,
            timeout=300,  # 5分タイムアウト
        )
        
        if result.returncode == 0:
            add_log("SUCCESS", f"実行成功: {script_path.name}")
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        else:
            add_log("ERROR", f"実行失敗: {script_path.name} (code: {result.returncode})")
            return {
                "success": False,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
    
    except subprocess.TimeoutExpired:
        add_log("ERROR", f"タイムアウト: {script_path.name}")
        return {"success": False, "error": "Timeout (5分以上)"}
    
    except Exception as e:
        add_log("ERROR", f"実行エラー: {str(e)}")
        return {"success": False, "error": str(e)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# エンドポイント
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/")
def read_root():
    return {
        "service": "Sentinel Personal API",
        "version": "1.0.0",
        "endpoints": [
            "POST /api/generate-strategies",
            "POST /api/generate-articles",
            "POST /api/ai-judge",
            "POST /api/scrape-news",
            "GET  /api/quote/{ticker}",
            "GET  /api/historical/{ticker}",
            "GET  /api/fundamentals/{ticker}",
            "GET  /api/status",
            "GET  /api/logs",
        ]
    }

@app.get("/api/status")
def get_status():
    """システム状態確認"""
    scripts_dir = PROJECT_ROOT / "scripts"
    content_dir = PROJECT_ROOT / "frontend" / "public" / "content"
    
    # 最新ファイル確認
    strategies_file = content_dir / "strategies.json"
    articles_index = content_dir / "index.json"
    
    strategies_mtime = None
    if strategies_file.exists():
        strategies_mtime = datetime.fromtimestamp(strategies_file.stat().st_mtime).isoformat()
    
    articles_mtime = None
    if articles_index.exists():
        articles_mtime = datetime.fromtimestamp(articles_index.stat().st_mtime).isoformat()
    
    return {
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "files": {
            "strategies.json": {
                "exists": strategies_file.exists(),
                "last_modified": strategies_mtime,
            },
            "index.json": {
                "exists": articles_index.exists(),
                "last_modified": articles_mtime,
            }
        },
        "scripts": {
            "generate_strategies.py": (scripts_dir / "generate_strategies.py").exists(),
            "generate_articles.py": (scripts_dir / "generate_articles.py").exists(),
            "ai_judge.py": (scripts_dir / "ai_judge.py").exists(),
            "scrape_news.py": (scripts_dir / "scrape_news.py").exists(),
        }
    }

@app.get("/api/logs")
def get_logs(limit: int = 50):
    """実行ログ取得"""
    logs = []
    temp_queue = queue.Queue()
    
    # キューからログを取り出し
    while not log_queue.empty():
        log = log_queue.get()
        logs.append(log)
        temp_queue.put(log)
    
    # ログを戻す
    while not temp_queue.empty():
        log_queue.put(temp_queue.get())
    
    # 新しい順にソート
    logs.reverse()
    
    return {
        "total": len(logs),
        "logs": logs[:limit]
    }

@app.post("/api/generate-strategies")
async def generate_strategies(background_tasks: BackgroundTasks):
    """全銘柄スキャン実行（バックグラウンド）"""
    script = PROJECT_ROOT / "scripts" / "generate_strategies.py"
    
    if not script.exists():
        raise HTTPException(status_code=404, detail="generate_strategies.py が見つかりません")
    
    # バックグラウンドで実行
    def run_in_background():
        result = run_script(script)
        if result["success"]:
            add_log("SUCCESS", "全銘柄スキャン完了")
        else:
            add_log("ERROR", f"スキャン失敗: {result.get('error', 'Unknown')}")
    
    background_tasks.add_task(run_in_background)
    
    return {
        "status": "started",
        "message": "全銘柄スキャンをバックグラウンドで開始しました",
        "estimated_time": "5-10分"
    }

@app.post("/api/generate-articles")
async def generate_articles(background_tasks: BackgroundTasks):
    """日次レポート生成（バックグラウンド）"""
    script = PROJECT_ROOT / "scripts" / "generate_articles.py"
    
    if not script.exists():
        raise HTTPException(status_code=404, detail="generate_articles.py が見つかりません")
    
    def run_in_background():
        result = run_script(script)
        if result["success"]:
            add_log("SUCCESS", "日次レポート生成完了")
        else:
            add_log("ERROR", f"レポート生成失敗: {result.get('error', 'Unknown')}")
    
    background_tasks.add_task(run_in_background)
    
    return {
        "status": "started",
        "message": "日次レポート生成をバックグラウンドで開始しました",
        "estimated_time": "2-5分"
    }

@app.post("/api/ai-judge")
async def ai_judge(request: AIJudgeRequest):
    """AI判断実行（同期）"""
    script = PROJECT_ROOT / "scripts" / "ai_judge.py"
    
    if not script.exists():
        raise HTTPException(status_code=404, detail="ai_judge.py が見つかりません")
    
    ticker = request.ticker.upper()
    add_log("INFO", f"AI判断開始: {ticker}")
    
    result = run_script(script, args=[ticker])
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"AI判断失敗: {result.get('error', 'Unknown')}")
    
    # 生成されたJSONを読み込み
    judgment_file = PROJECT_ROOT / "frontend" / "public" / "content" / f"{ticker.lower()}_judgment.json"
    
    if judgment_file.exists():
        judgment_data = json.loads(judgment_file.read_text(encoding='utf-8'))
        add_log("SUCCESS", f"AI判断完了: {ticker} → {judgment_data['judgment']['judgment']}")
        return judgment_data
    else:
        raise HTTPException(status_code=500, detail="判断ファイルが生成されませんでした")

@app.post("/api/scrape-news")
async def scrape_news(request: NewsRequest):
    """ニュース収集実行（同期）"""
    script = PROJECT_ROOT / "scripts" / "scrape_news.py"
    
    if not script.exists():
        raise HTTPException(status_code=404, detail="scrape_news.py が見つかりません")
    
    ticker = request.ticker.upper()
    add_log("INFO", f"ニュース収集開始: {ticker}")
    
    result = run_script(script, args=[ticker])
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"ニュース収集失敗: {result.get('error', 'Unknown')}")
    
    # 生成されたJSONを読み込み
    news_file = PROJECT_ROOT / "frontend" / "public" / "content" / f"{ticker.lower()}_news.json"
    
    if news_file.exists():
        news_data = json.loads(news_file.read_text(encoding='utf-8'))
        add_log("SUCCESS", f"ニュース収集完了: {ticker} ({news_data['total_count']}件)")
        return news_data
    else:
        raise HTTPException(status_code=500, detail="ニュースファイルが生成されませんでした")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FMP API 直接エンドポイント
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/api/quote/{ticker}")
async def get_quote(ticker: str):
    """リアルタイム株価取得（FMP直接）"""
    ticker = ticker.upper()
    add_log("INFO", f"株価取得: {ticker}")
    
    try:
        # FMP quote エンドポイント
        data = fmp_get(f"quote/{ticker}")
        
        if not data or len(data) == 0:
            raise HTTPException(status_code=404, detail=f"{ticker} のデータが見つかりません")
        
        quote = data[0]
        
        # 整形
        result = {
            "ticker": ticker,
            "price": quote.get("price"),
            "change": quote.get("change"),
            "changesPercentage": quote.get("changesPercentage"),
            "dayHigh": quote.get("dayHigh"),
            "dayLow": quote.get("dayLow"),
            "open": quote.get("open"),
            "previousClose": quote.get("previousClose"),
            "volume": quote.get("volume"),
            "marketCap": quote.get("marketCap"),
            "timestamp": datetime.now().isoformat(),
        }
        
        add_log("SUCCESS", f"株価取得完了: {ticker} ${result['price']}")
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        add_log("ERROR", f"株価取得エラー: {ticker} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/historical/{ticker}")
async def get_historical(ticker: str, days: int = 365):
    """過去株価取得（FMP直接）"""
    ticker = ticker.upper()
    add_log("INFO", f"過去株価取得: {ticker} ({days}日)")
    
    try:
        # FMP historical-price-eod エンドポイント
        data = fmp_get("historical-price-eod/full", {"symbol": ticker})
        
        # Stable APIはリスト形式で返す
        hist = data if isinstance(data, list) else data.get("historical", [])
        
        if not hist:
            raise HTTPException(status_code=404, detail=f"{ticker} の過去データが見つかりません")
        
        # 直近N日分
        result = hist[:days] if len(hist) > days else hist
        
        add_log("SUCCESS", f"過去株価取得完了: {ticker} ({len(result)}日)")
        return {
            "ticker": ticker,
            "days": len(result),
            "data": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        add_log("ERROR", f"過去株価取得エラー: {ticker} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fundamentals/{ticker}")
async def get_fundamentals(ticker: str):
    """ファンダメンタルデータ取得（複数ソース統合）"""
    ticker = ticker.upper()
    add_log("INFO", f"ファンダメンタル取得: {ticker}")
    
    try:
        # 複数エンドポイントから取得
        ratios = fmp_get("ratios-ttm", {"symbol": ticker})
        profile = fmp_get(f"profile/{ticker}")
        
        ratios_data = ratios[0] if isinstance(ratios, list) and ratios else {}
        profile_data = profile[0] if isinstance(profile, list) and profile else {}
        
        result = {
            "ticker": ticker,
            "name": profile_data.get("companyName"),
            "sector": profile_data.get("sector"),
            "pe": ratios_data.get("priceEarningsRatioTTM"),
            "marketCap": profile_data.get("mktCap"),
            "eps": ratios_data.get("epsGrowthTTM"),
            "revenueGrowth": ratios_data.get("revenueGrowthTTM"),
            "profitMargin": ratios_data.get("netProfitMarginTTM"),
            "debtToEquity": ratios_data.get("debtEquityRatioTTM"),
        }
        
        add_log("SUCCESS", f"ファンダメンタル取得完了: {ticker}")
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        add_log("ERROR", f"ファンダメンタル取得エラー: {ticker} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 起動
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import uvicorn
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🛡️  SENTINEL PERSONAL BACKEND SERVER                       ║
║                                                               ║
║   FastAPI powered backend for Sentinel Personal              ║
║   http://localhost:8000                                       ║
║   Docs: http://localhost:8000/docs                            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
