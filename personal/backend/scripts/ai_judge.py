import os, json, sys, requests, re
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import io
import xml.etree.ElementTree as ET   # ← Google RSS用（標準ライブラリ）

# ── 0. 文字化け・環境対策 ──────────────────────────────────
if os.name == 'nt':
    os.system('chcp 65001 > nul')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def dprint(msg):
    print(f"DEBUG: {msg}", flush=True)

dprint("Initializing Sentinel AI Engine...")

# ── 1. 環境設定 ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(env_path)
except ImportError:
    pass

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "shared"))

import yfinance as yf

from engines import core_fmp
from engines.analysis import VCPAnalyzer, RSAnalyzer
from engines.canslim import CANSLIMAnalyzer
from engines.ecr_strategy import ECRStrategyEngine
from engines.sentinel_efficiency import SentinelEfficiencyAnalyzer

API_KEY     = os.environ.get("OPENAI_API_KEY", "")
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
BASE_URL    = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL       = os.environ.get("OPENAI_MODEL", "gpt-4o")

if hasattr(core_fmp, 'FMP_API_KEY'):
    core_fmp.FMP_API_KEY = FMP_API_KEY

if not API_KEY or not FMP_API_KEY:
    print("❌ APIキーが設定されていません")
    sys.exit(1)

# ── キャッシュ設定 ─────────────────────────────────────────
CACHE_DIR = project_root / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache(ticker: str, key: str, expiry_hours: int = 24):
    cache_file = CACHE_DIR / f"{ticker}_{key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            cached_time = datetime.fromisoformat(data["cached_at"])
            if datetime.now() - cached_time < timedelta(hours=expiry_hours):
                dprint(f"Cache HIT: {ticker}_{key}")
                return data["value"]
        except:
            pass
    return None

def save_cache(ticker: str, key: str, value):
    cache_file = CACHE_DIR / f"{ticker}_{key}.json"
    cache_file.write_text(json.dumps({
        "cached_at": datetime.now().isoformat(),
        "value": value
    }, ensure_ascii=False, default=str), encoding='utf-8')

# ── 2. システムプロンプト ───────────────────────────────────
SYSTEM_PROMPT = """あなたは機関投資家レベルのプロフェッショナル・トレーダーです。
提供された「計算済みデータ」を**絶対に尊重**し、独自に再計算してはいけません。

【VCP評価】
・スコア53点（tightness30 + volume0 + ma20 + pivot3）をそのまま使用

【CANSLIM】
・I: Institutional 65.32% → 良好

回答は必ず以下のJSON形式（内容は日本語）:
{
  "judgment": "BUY" | "WAIT" | "SELL",
  "confidence": 0-100,
  "vcp_score_breakdown": {"tightness": 0, "volume": 0, "ma": 0, "pivot": 0},
  "reasoning": "200字以内。各数値を具体的に言及",
  "entry_plan": "具体的な価格",
  "risks": ["リスク1", "リスク2"],
  "catalysts": ["材料1", "材料2"]
}
"""

# ── 3. データ取得関数 ───────────────────────────────────

def clean_val(val):
    if val is None: return None
    s = str(val).replace(',', '').strip()
    s = re.sub(r'<[^>]+>', '', s)
    match = re.search(r'([-0-9\.\%KMBT]+)', s)
    return match.group(1).strip() if match else None

def fetch_fmp_fundamentals(ticker: str) -> dict:
    cached = get_cache(ticker, "fmp_fund")
    if cached: return cached
    dprint(f"FMP fundamentals for {ticker}")
    try:
        ratios_resp = core_fmp._get(f"{core_fmp.BASE_URL}/ratios-ttm", {"symbol": ticker})
        ratios = ratios_resp[0] if isinstance(ratios_resp, list) and ratios_resp else {}

        km_resp = core_fmp._get(f"{core_fmp.BASE_URL}/key-metrics", {"symbol": ticker, "period": "annual", "limit": 1})
        km = km_resp[0] if isinstance(km_resp, list) and km_resp else {}

        profile = core_fmp.get_company_profile(ticker) or {}

        mcap_resp = core_fmp._get(f"{core_fmp.BASE_URL}/market-capitalization", {"symbol": ticker})
        mcap_value = mcap_resp.get("marketCap") if isinstance(mcap_resp, dict) else None

        eps = None
        try:
            inc_resp = core_fmp._get(f"{core_fmp.BASE_URL}/income-statement", {"symbol": ticker, "period": "annual", "limit": 1})
            if isinstance(inc_resp, list) and inc_resp:
                eps = clean_val(inc_resp[0].get("epsdiluted")) or clean_val(inc_resp[0].get("eps"))
        except:
            pass

        result = {
            "pe": clean_val(ratios.get("priceEarningsRatioTTM")) or clean_val(km.get("peRatioTTM")) or clean_val(profile.get("trailingPE")) or clean_val(profile.get("forwardPE")),
            "market_cap": clean_val(mcap_value) or clean_val(ratios.get("marketCapTTM")) or clean_val(km.get("marketCapTTM")) or clean_val(profile.get("mktCap")) or clean_val(profile.get("marketCap")),
            "eps_growth": clean_val(ratios.get("epsGrowthTTM")) or clean_val(km.get("epsGrowthTTM")) or None,
            "rev_growth": clean_val(ratios.get("revenueGrowthTTM")) or clean_val(km.get("revenueGrowthTTM")) or None,
            "inst_pct": clean_val(profile.get("institutionalOwnershipPercentage")),
            "eps": eps,
        }
        save_cache(ticker, "fmp_fund", result)
        return result
    except Exception as e:
        dprint(f"FMP fund error: {e}")
        result = {"pe": None, "market_cap": None, "eps_growth": None, "rev_growth": None, "inst_pct": None, "eps": None}
        save_cache(ticker, "fmp_fund", result)
        return result

def fetch_yahoo_finance(ticker: str) -> dict:
    cached = get_cache(ticker, "yahoo")
    if cached: return cached
    dprint(f"Yahoo Finance for {ticker} (yfinance)")
    res = {"pe": None, "market_cap": None, "inst_pct": None}
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        res["pe"] = info.get("trailingPE") or info.get("forwardPE")
        res["market_cap"] = info.get("marketCap")
        inst_raw = info.get("heldPercentInstitutions")
        if inst_raw is not None:
            res["inst_pct"] = round(inst_raw * 100, 2)
            dprint(f"✅ 機関保有率: {res['inst_pct']}%")
    except Exception as e:
        dprint(f"yfinance error: {e}")
    save_cache(ticker, "yahoo", res)
    return res

# ── ★新関数★ Google News RSS（これがメイン！） ─────────────────
def fetch_google_news(ticker: str) -> list:
    cached = get_cache(ticker, "google_news", expiry_hours=6)
    if cached: return cached
    dprint(f"Google News RSS for {ticker}")
    news = []
    try:
        # 日本語ニュース優先
        url = f"https://news.google.com/rss/search?q={ticker}&hl=ja-JP&gl=JP&ceid=JP:ja"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        for item in root.findall('.//item')[:8]:
            title_elem = item.find('title')
            if title_elem is not None and title_elem.text:
                news.append(title_elem.text.strip())
        dprint(f"✅ Google News {len(news)}件取得")
    except Exception as e:
        dprint(f"Google News error: {e}")
        news = ["Google News取得中..."]
    save_cache(ticker, "google_news", news)
    return news

def get_rs_from_strategies(ticker: str) -> int:
    try:
        strat_file = project_root / "frontend" / "public" / "content" / "strategies.json"
        if not strat_file.exists(): return 0
        strat = json.loads(strat_file.read_text(encoding='utf-8'))
        for ranking in strat.get("rankings", {}).values():
            if isinstance(ranking, list):
                for item in ranking:
                    if item.get("ticker") == ticker:
                        return item.get("scores", {}).get("rs", 0)
        return 0
    except:
        return 0

def build_context(ticker: str) -> dict:
    cached = get_cache(ticker, "context", expiry_hours=12)
    if cached: return cached
    dprint(f"Building context for {ticker}")
    df = core_fmp.get_historical_data(ticker, days=400)
    if df is None or len(df) < 50:
        dprint(f"{ticker}: No historical data")
        return None

    vcp = VCPAnalyzer.calculate(df)
    rs_raw = RSAnalyzer.get_raw_score(df)
    rs_pct = get_rs_from_strategies(ticker) or (min(99, max(0, int((rs_raw + 0.3) * 100))) if rs_raw != -999.0 else 0)

    canslim = CANSLIMAnalyzer.calculate(ticker, df)
    ecr = ECRStrategyEngine.analyze_single(ticker, df)
    ses = SentinelEfficiencyAnalyzer.calculate(df)

    profile = core_fmp.get_company_profile(ticker) or {}
    try:
        analyst = core_fmp.get_analyst_consensus(ticker) or {}
    except:
        analyst = {}

    fmp_fund = fetch_fmp_fundamentals(ticker)
    y_data = fetch_yahoo_finance(ticker)
    google_news = fetch_google_news(ticker)   # ← ここが新！

    pe = fmp_fund["pe"] or y_data["pe"]
    market_cap = fmp_fund["market_cap"] or y_data["market_cap"]
    inst_pct = fmp_fund["inst_pct"] or y_data["inst_pct"]

    price = round(float(df["Close"].iloc[-1]), 2)

    if pe is not None:
        try:
            pe_float = float(pe)
            if pe_float < 10 and fmp_fund.get("eps") is not None:
                eps_value = float(fmp_fund["eps"])
                if eps_value > 0:
                    calculated_pe = round(price / eps_value, 2)
                    if 10 < calculated_pe < 50:
                        pe = calculated_pe
        except:
            pass

    news_fmp = core_fmp.get_news(ticker, limit=15)
    news_lines = ["【Market Intelligence News】"]
    for n in news_fmp:
        title = n.get('title', '')
        if ticker in title or profile.get("companyName", "").split()[0] in title:
            news_lines.append(f"- {n.get('published_at', '')[:10]}: {title}")

    # Google Newsをメインに使用
    if google_news and google_news[0] != "Google News取得中...":
        news_lines.append("【Google News】")
        news_lines.extend([f"- {n}" for n in google_news])
    else:
        news_lines.append("【Google News】")
        news_lines.extend([f"- {n}" for n in google_news])

    if len(news_lines) <= 2:
        news_lines.append(f"No recent news found for {ticker}.")

    result = {
        "ticker": ticker,
        "name": profile.get("companyName", ticker),
        "price": price,
        "pivot": round(float(df["High"].iloc[-20:].max()), 2),
        "scores": {
            "vcp": vcp.get("score", 0),
            "rs": rs_pct,
            "canslim": canslim.get("score", 0),
            "ecr_rank": ecr.get("sentinel_rank", 0),
            "ses": ses.get("score", 0),
        },
        "vcp_details": vcp,
        "ses_details": ses,
        "ecr_phase": ecr.get("phase", "WATCH"),
        "fundamentals": {
            "pe": pe,
            "eps_growth": fmp_fund["eps_growth"] or canslim["metrics"].get("eps_growth"),
            "rev_growth": fmp_fund["rev_growth"] or canslim["metrics"].get("rev_growth"),
            "market_cap": market_cap,
        },
        "analyst": analyst,
        "ownership": {"institutional_pct": inst_pct},
        "news": "\n".join(news_lines)
    }
    save_cache(ticker, "context", result)
    return result

def ask_ai(context: dict) -> dict:
    dprint(f"Deploying AI analysis ({MODEL})...")
    user_msg = f"""
分析対象: {context['ticker']} ({context['name']})
株価: ${context['price']} / Pivot: ${context['pivot']}

【VCP詳細】
スコア: {context['scores']['vcp']}点（tightness={context['vcp_details'].get('breakdown',{}).get('tight',0)}, volume={context['vcp_details'].get('breakdown',{}).get('vol',0)}, ma={context['vcp_details'].get('breakdown',{}).get('ma',0)}, pivot={context['vcp_details'].get('breakdown',{}).get('pivot',0)}）

【CANSLIM・ファンダメンタル】
CANSLIM Score: {context['scores']['canslim']}
EPS成長: {context['fundamentals']['eps_growth']}% / 売上成長: {context['fundamentals']['rev_growth']}%
機関保有率: {context['ownership']['institutional_pct'] or 'N/A'}%

【その他】
RS: {context['scores']['rs']}
SES: {context['scores']['ses']}
ECR Phase: {context['ecr_phase']}

【最新ニュース】
{context['news']}
"""

    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_msg}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"AI API error: {e}")
        return {"judgment": "ERROR", "confidence": 0, "reasoning": str(e)}

def main():
    if len(sys.argv) < 2:
        print("Usage: python ai_judge.py TICKER")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    print(f"\n=== SENTINEL AI JUDGE: {ticker} (Strict Protocol) ===\n")
    
    context = build_context(ticker)
    if not context:
        print(f"❌ {ticker}: データの取得に失敗しました。")
        sys.exit(1)
    
    try:
        judgment = ask_ai(context)
        
        print(f"{'━'*60}")
        print(f"判定: {judgment.get('judgment', 'ERROR')} (信頼度: {judgment.get('confidence', 0)}%)")
        print(f"VCP内訳: {judgment.get('vcp_score_breakdown')}")
        print(f"判断理由: {judgment.get('reasoning', '不明')}")
        print(f"{'━'*60}")

        out = {
            "generated_at": datetime.now().isoformat(),
            "ticker": ticker,
            "context": context,
            "judgment": judgment
        }
        
        out_dir = project_root.parent / "frontend" / "public" / "content"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{ticker.lower()}_judgment.json"
        
        json_data = json.dumps(out, indent=2, ensure_ascii=False)
        out_file.write_text(json_data, encoding='utf-8')
        print(json_data)
        
        print(f"\n✅ 保存完了: {out_file}")

    except Exception as e:
        print(f"❌ 診断エラーが発生しました: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()