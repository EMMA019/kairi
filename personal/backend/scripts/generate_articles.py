#!/usr/bin/env python3
"""
scripts/generate_articles.py — 軽量・データ統合版 (Google RSS内蔵)
====================================
事前に計算されたスコアJSON（例: 2026-02-19.json）を読み込み、
上位銘柄の最新ニュースをGoogle News RSSから動的に取得。
それらを統合してAIに分析させ、ダッシュボード用のレポートと目次を生成する。

[変更点]
enrich_top_actions() のエントリー/ストップ/ターゲット計算を
固定%方式 → ATRベース方式に改修。
strategies.jsonのall_dataからATR・pivotを取得して使用。
★追加修正: all_dataだけでなくrankingsからも最新の価格を取得し、ズレを解消。
"""
import sys, json, os, time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests

# パス設定
sys.path.append(str(Path(__file__).parent.parent / "shared"))
from engines import core_fmp

# 環境設定
JST = timezone(timedelta(hours=9))
CONTENT_DIR = Path(r"D:\program\personal\frontend\public\content")
CONTENT_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL    = os.environ.get("OPENAI_MODEL", "gpt-4o")


def get_latest_trading_date() -> str:
    """現在の日付を取得（引数で指定されていればそれを使う）"""
    if len(sys.argv) > 1 and sys.argv[1].count('-') == 2:
        return sys.argv[1]
    return datetime.now(JST).strftime("%Y-%m-%d")


def load_scores_json(date_str: str) -> list:
    """指定された日付のスコアJSONを読み込む"""
    paths_to_check = [
        CONTENT_DIR / f"{date_str}.json",
        CONTENT_DIR / "strategies_history" / f"{date_str}.json",
        Path(__file__).parent.parent / f"{date_str}.json"
    ]
    for p in paths_to_check:
        if p.exists():
            print(f"✅ スコアデータを読み込みました: {p.name}")
            return json.loads(p.read_text(encoding='utf-8'))

    print(f"❌ {date_str}.json が見つかりません。")
    sys.exit(1)


def load_strategies_detail() -> dict:
    """
    strategies.jsonのall_dataとrankingsからATR・pivot・価格等の詳細データを
    tickerキーで引けるmapを作る。
    """
    strat_file = CONTENT_DIR / "strategies.json"
    if not strat_file.exists():
        print("⚠️  strategies.json が見つかりません。ATRフォールバックで動作します。")
        return {}

    try:
        strat = json.loads(strat_file.read_text(encoding='utf-8'))
        detail_map = {}
        
        # まずは all_data を読み込む
        for item in strat.get("all_data", []):
            ticker = item.get("ticker")
            if ticker:
                detail_map[ticker] = {
                    "price":          item.get("price", 0.0),
                    "atr":            item.get("vcp_details", {}).get("atr", 0.0),
                    "atr_pct":        item.get("atr_pct", 0.0),
                    "pivot":          item.get("pivot", 0.0),
                    "pivot_dist_pct": item.get("pivot_dist_pct", 0.0),
                    "vcp_score":      item.get("scores", {}).get("vcp", 0),
                    "ma50_ratio":     item.get("ma50_ratio", 0.0),
                }
                
        # 【修正箇所】価格のズレを防ぐため、最新情報を持つ rankings 側で上書きする
        for item in strat.get("rankings", {}).get("vcp_rs", []):
            ticker = item.get("ticker")
            if ticker:
                detail_map[ticker] = {
                    "price":          item.get("price", 0.0),  # 最新の価格
                    "atr":            item.get("vcp_details", {}).get("atr", 0.0),
                    "atr_pct":        item.get("atr_pct", 0.0),
                    "pivot":          item.get("pivot", 0.0),
                    "pivot_dist_pct": item.get("pivot_dist_pct", 0.0),
                    "vcp_score":      item.get("scores", {}).get("vcp", 0),
                    "ma50_ratio":     item.get("ma50_ratio", 0.0),
                }

        print(f"✅ strategies.json から {len(detail_map)} 銘柄の詳細データを読み込みました")
        return detail_map
    except Exception as e:
        print(f"⚠️  strategies.json 読み込みエラー: {e}")
        return {}


def calc_entry_levels(price: float, detail: dict) -> dict:
    """
    ATRベースのエントリー/ストップ/ターゲットを計算する。

    ロジック:
    ─────────────────────────────────────────────────────
    ATR有効 (atr > 0 かつ atr_pct <= 8%) の場合:

      【VCP高スコア (>=70) かつ pivot近辺 (-5%〜+3%)】
        → pivot ブレイクアウトエントリー
        entry  = pivot × 1.005  (pivot上0.5%でブレイク確認)
        stop   = entry - ATR × 1.5
        target = entry + ATR × 3.0  (RR ≈ 1:2.0)

      【VCP中スコア (50-69)】
        → 現値スライトアバブエントリー
        entry  = price × 1.005
        stop   = entry - ATR × 1.5
        target = entry + ATR × 2.5  (RR ≈ 1:1.7)

      【VCP低スコア (<50)】
        → 現値エントリー（様子見気味）
        entry  = price × 1.01
        stop   = entry - ATR × 2.0  (少し広め)
        target = entry + ATR × 2.0  (RR ≈ 1:1.0)

    ATR無効 または atr_pct > 8% の場合 (高ボラ・バイオ等):
        → 固定%フォールバック（従来方式）
        entry  = price × 1.01
        stop   = entry × 0.94   (6% stop)
        target = entry × 1.12   (12% target / RR ≈ 1:2.0)

    Returns:
        {"entry": float, "stop": float, "target": float,
         "rr": float, "method": str, "atr_used": float}
    ─────────────────────────────────────────────────────
    """
    if price <= 0:
        return {"entry": 0, "stop": 0, "target": 0, "rr": 0, "method": "no_price", "atr_used": 0}

    atr         = detail.get("atr", 0.0)
    atr_pct     = detail.get("atr_pct", 0.0)
    pivot       = detail.get("pivot", 0.0)
    pivot_dist  = detail.get("pivot_dist_pct", 0.0)  # 負 = pivot超え済み、正 = まだ届いてない
    vcp_score   = detail.get("vcp_score", 0)

    # ── ATR有効判定 ─────────────────────────────────────
    atr_valid = (atr > 0) and (0 < atr_pct <= 8.0)

    if atr_valid:
        # ── ① VCP高スコア + pivot近辺 ────────────────────
        if vcp_score >= 70 and pivot > 0 and -5.0 <= pivot_dist <= 3.0:
            entry  = round(pivot * 1.005, 2)
            stop   = round(entry - atr * 1.5, 2)
            target = round(entry + atr * 3.0, 2)
            method = "pivot_breakout"

        # ── ② VCP中スコア ────────────────────────────────
        elif vcp_score >= 50:
            entry  = round(price * 1.005, 2)
            stop   = round(entry - atr * 1.5, 2)
            target = round(entry + atr * 2.5, 2)
            method = "price_above_atr"

        # ── ③ VCP低スコア ────────────────────────────────
        else:
            entry  = round(price * 1.01, 2)
            stop   = round(entry - atr * 2.0, 2)
            target = round(entry + atr * 2.0, 2)
            method = "watchlist_atr"

        # ストップがマイナスになる異常値チェック
        if stop <= 0 or stop >= entry:
            # フォールバックへ
            atr_valid = False

    if not atr_valid:
        # ── フォールバック（固定%） ───────────────────────
        entry  = round(price * 1.01, 2)
        stop   = round(entry * 0.94, 2)   # -6%
        target = round(entry * 1.12, 2)   # +12%
        method = "fallback_pct"
        atr    = 0.0

    # RR計算
    risk   = entry - stop
    reward = target - entry
    rr     = round(reward / risk, 2) if risk > 0 else 0.0

    return {
        "entry":    entry,
        "stop":     stop,
        "target":   target,
        "rr":       rr,
        "method":   method,
        "atr_used": round(atr, 2),
    }


def fetch_google_news(ticker: str) -> dict:
    """Google News RSSから記事を取得し、簡易センチメント分析を行う"""
    url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"

    pos_words = ['beat', 'upgrade', 'buy', 'strong', 'growth', 'surge', 'bullish', 'outperform', 'raise', 'target', 'higher', 'rally', 'breakout']
    neg_words = ['miss', 'downgrade', 'sell', 'weak', 'decline', 'drop', 'bearish', 'underperform', 'cut', 'lower', 'loss', 'warning', 'investigation']
    cat_words = ['earnings', 'guidance', 'acquisition', 'merger', 'partnership', 'fda', 'approval', 'clinical', 'dividend', 'buyback', 'split', 'launch']

    try:
        resp = requests.get(url, timeout=10)
        root = ET.fromstring(resp.content)

        articles = []
        for item in root.findall('./channel/item')[:5]:
            title = item.find('title').text if item.find('title') is not None else ""
            articles.append(title)

        if not articles:
            return {}

        text_content = " ".join(articles).lower()
        pos_count = sum(1 for w in pos_words if w in text_content)
        neg_count = sum(1 for w in neg_words if w in text_content)
        cat_count = sum(1 for w in cat_words if w in text_content)

        total = pos_count + neg_count
        score = (pos_count - neg_count) / total * 100 if total > 0 else 0
        label = 'Bullish' if score > 30 else 'Bearish' if score < -30 else 'Neutral'
        cat_str = 'Strong' if cat_count >= 2 else 'Medium' if cat_count == 1 else 'Weak'

        return {
            "score":             round(score, 1),
            "label":             label,
            "catalyst_strength": cat_str,
            "catalyst_count":    cat_count,
            "article_count":     len(articles),
            "headlines":         articles[:3]
        }
    except Exception as e:
        print(f"  ⚠️ RSS取得エラー({ticker}): {e}")
        return {}


def enrich_top_actions(scores: list, detail_map: dict) -> list:
    """
    ACTION銘柄の上位にFMPプロファイル・ニュース・ATRエントリーを結合する。
    detail_map: strategies.jsonから読み込んだティッカー別詳細データ
    """
    actions = [s for s in scores if s.get("status") == "ACTION"]
    actions.sort(
        key=lambda x: x.get("scores", {}).get("composite",
            x.get("scores", {}).get("vcp", 0) + x.get("scores", {}).get("rs", 0)),
        reverse=True
    )

    enriched = []
    max_enrich = 30
    method_counts = {}

    print(f"\n--- Top {max_enrich} ACTION銘柄のデータエンリッチメント (ATRベース) ---")

    for i, item in enumerate(actions[:max_enrich]):
        ticker = item["ticker"]
        sc     = item["scores"]

        # 1. FMPから最新プロファイルを取得 (セクター等用)
        profile = core_fmp.get_company_profile(ticker) or {}
        sector  = profile.get("sector", "N/A")

        # 2. strategies.jsonから詳細データ（最新価格・ATR等）を取得
        detail = detail_map.get(ticker, {})

        # 【修正箇所】strategies.json の最新価格を最優先にする
        price = detail.get("price", 0.0)
        
        # もし strategies.json に価格がなければ FMP の価格をフォールバックとして使う
        if price <= 0:
            price = float(profile.get("price", 0.0))
            
        # それでもダメなら pivot の少し下を推定値とする
        if price <= 0:
            price = detail.get("pivot", 0.0) * 0.97  

        # 3. ATRベースのエントリー計算
        levels = calc_entry_levels(price, detail)
        method_counts[levels["method"]] = method_counts.get(levels["method"], 0) + 1

        # 4. Google News RSSからニュースセンチメントを取得
        news_data = fetch_google_news(ticker)

        enriched.append({
            "ticker":        ticker,
            "name":          profile.get("companyName", ticker)[:20],
            "sector":        sector,
            "status":        "ACTION",
            "vcp":           sc.get("vcp", 0),
            "rs":            sc.get("rs", 0),
            "canslim_score": sc.get("canslim", 0),
            "composite":     sc.get("composite", 0),
            "_price":        round(price, 2),
            "_entry":        levels["entry"],
            "_stop":         levels["stop"],
            "_target":       levels["target"],
            "_rr":           levels["rr"],
            "_entry_method": levels["method"],   # デバッグ・フロントエンド表示用
            "_atr_used":     levels["atr_used"],
            "news_summary":  news_data,
        })

        news_status = f"📰 {news_data.get('label', 'None')}" if news_data else "No news"
        print(
            f" [{i+1:2d}] {ticker:6s} ${price:8.2f}"
            f"  Entry=${levels['entry']:8.2f}  Stop=${levels['stop']:8.2f}"
            f"  Target=${levels['target']:8.2f}  RR=1:{levels['rr']:.1f}"
            f"  [{levels['method']:20s}]  {news_status}"
        )
        time.sleep(0.05)

    # 採用メソッドの内訳を表示
    print(f"\n--- エントリー計算メソッド内訳 ---")
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        label = {
            "pivot_breakout":  "Pivot Breakout (ATR×1.5/3.0)",
            "price_above_atr": "Price Above ATR (ATR×1.5/2.5)",
            "watchlist_atr":   "Watchlist ATR   (ATR×2.0/2.0)",
            "fallback_pct":    "Fallback 固定%  (−6%/+12%)",
        }.get(method, method)
        print(f"  {label}: {count}件")

    return enriched


def build_sector_summary(enriched_actions: list) -> list:
    """上位銘柄から強いセクターを抽出"""
    sec_counts = {}
    for a in enriched_actions:
        s = a["sector"]
        if s == "N/A":
            continue
        if s not in sec_counts:
            sec_counts[s] = {"action_count": 0, "vcp_sum": 0}
        sec_counts[s]["action_count"] += 1
        sec_counts[s]["vcp_sum"] += a["vcp"]

    return sorted([{
        "sector":       s,
        "action_count": v["action_count"],
        "avg_vcp":      round(v["vcp_sum"] / v["action_count"], 1)
    } for s, v in sec_counts.items()], key=lambda x: x["action_count"], reverse=True)


def update_market_indices():
    """フロントエンド用の market.json を生成"""
    print("\n--- 市場指数(market.json)の更新 ---")
    indices = {"SPY": "S&P 500", "QQQ": "NASDAQ 100", "IWM": "Russell 2000"}
    market_data = {"indices": {}}

    for ticker, name in indices.items():
        try:
            df    = core_fmp.get_historical_data(ticker, days=30)
            price = core_fmp.get_company_profile(ticker).get("price", 0)
            if df is not None and len(df) >= 20:
                c = df["Close"]
                market_data["indices"][ticker] = {
                    "label": name,
                    "quote": {"price": price},
                    "performance": {
                        "ret_1d": round((c.iloc[-1]/c.iloc[-2]-1)*100, 2),
                        "ret_5d": round((c.iloc[-1]/c.iloc[-6]-1)*100, 2),
                        "ret_1m": round((c.iloc[-1]/c.iloc[-21]-1)*100, 2)
                    }
                }
        except Exception as e:
            print(f" ⚠️ {ticker} 取得エラー: {e}")

    out_path = CONTENT_DIR / "market.json"
    out_path.write_text(json.dumps(market_data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✅ market.json を保存しました")
    return market_data


def generate_ai_report(date_str: str, actions: list, sectors: list, market: dict) -> str:
    """AIにテクニカルとニュースを融合したレポートを書かせる"""
    print("\n--- AIレポート生成中 (激熱トーン)... ---")

    idx_info = []
    for t, d in market.get("indices", {}).items():
        idx_info.append(f"{d['label']}: 1日 {d['performance'].get('ret_1d', 0)}% / 1ヶ月 {d['performance'].get('ret_1m', 0)}%")

    ticker_info = ""
    for a in actions[:15]:
        sent = a.get("news_summary", {})
        if sent and sent.get("headlines"):
            news_text = f"センチメント: {sent.get('label')} / 触媒: {sent.get('catalyst_strength')} / 見出し: {', '.join(sent['headlines'])}"
        else:
            news_text = "最新ニュースなし"

        ticker_info += (
            f"- {a['ticker']} ({a['sector']}): VCP {a['vcp']}点, RS {a['rs']}点"
            f" | Entry=${a['_entry']} Stop=${a['_stop']} Target=${a['_target']} RR=1:{a['_rr']}"
            f" [{a['_entry_method']}]. {news_text}\n"
        )

    system = "あなたは機関投資家レベルの米国株式アナリストです。指定されたフォーマットに従い、教育的かつ情熱的な(激熱)トーンで、インサイトに富んだレポートを執筆してください。"

    prompt = f"""
日付: {date_str}

【市場データ】
{', '.join(idx_info)}

【セクター動向 (ACTION銘柄数順)】
{', '.join([f"{s['sector']}({s['action_count']}銘柄)" for s in sectors[:3]])}

【トップACTION銘柄とニュース・センチメント】
{ticker_info}

上記のデータ（特にテクニカルスコアとニュース見出しから読み取れる材料）を深く分析し、以下の3セクションで800〜1200文字程度の読み応えのある日本語レポートを作成してください。絵文字も適度に使って、市場の熱量(または冷え込み)を表現してください。
## ① 指数動向と市場全体のモメンタム分析
## ② 厳選ACTION銘柄：テクニカル×ファンダメンタルズの合致点
## ③ セクターローテーションの予兆と次なる戦略
"""
    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.7
            },
            timeout=180
        )
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"AIエラー: {e}")
        return "レポートの生成に失敗しました。"


def main():
    report_date = get_latest_trading_date()
    print(f"====== SENTINEL DAILY GENERATOR ({report_date}) ======")

    # 1. スコアデータ読み込み
    scores = load_scores_json(report_date)
    action_count = sum(1 for s in scores if s.get("status") == "ACTION")
    wait_count   = sum(1 for s in scores if s.get("status") == "WAIT")
    print(f"📊 データロード完了: 全{len(scores)}銘柄 (ACTION: {action_count}, WAIT: {wait_count})")

    # 2. strategies.jsonから詳細データ（ATR・pivot・価格等）を読み込む
    detail_map = load_strategies_detail()

    # 3. データのエンリッチメント (FMP + ATRエントリー + Google News RSS)
    enriched_actions = enrich_top_actions(scores, detail_map)
    sectors = build_sector_summary(enriched_actions)

    # 4. マーケットデータ取得
    market_data = update_market_indices()

    # 5. AIレポート生成
    ai_body = generate_ai_report(report_date, enriched_actions, sectors, market_data)

    # 6. daily-{DATE}.json の構築
    idx_spy_ret = market_data.get("indices", {}).get("SPY", {}).get("performance", {}).get("ret_1d", "?")

    daily_article = {
        "slug":         f"daily-{report_date}",
        "type":         "daily",
        "date":         report_date,
        "published_at": datetime.now(JST).isoformat(),
        "ja": {
            "title": f"{report_date} 米国株レポート — SPY {idx_spy_ret}% / ACTION {action_count}銘柄",
            "body":  ai_body,
        },
        "data": {
            "action_count": action_count,
            "wait_count":   wait_count,
            "actions":      enriched_actions,
            "sector":       sectors,
        }
    }

    out_file = CONTENT_DIR / f"daily-{report_date}.json"
    out_file.write_text(json.dumps(daily_article, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✅ Dailyレポート保存: {out_file.name}")

    # 7. index.json の更新
    index_file = CONTENT_DIR / "index.json"
    idx_data = {"articles": []}
    if index_file.exists():
        try:
            idx_data = json.loads(index_file.read_text(encoding='utf-8'))
        except:
            pass

    idx_data["articles"] = [a for a in idx_data.get("articles", []) if a.get("slug") != daily_article["slug"]]
    idx_data["articles"].insert(0, {
        "slug":       daily_article["slug"],
        "type":       daily_article["type"],
        "date":       daily_article["date"],
        "published_at": daily_article["published_at"],
        "title_ja":   daily_article["ja"]["title"]
    })

    index_file.write_text(json.dumps(idx_data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✅ index.json 更新完了 (総記事数: {len(idx_data['articles'])})")
    print("====== 処理完了 ======")


if __name__ == "__main__":
    main()