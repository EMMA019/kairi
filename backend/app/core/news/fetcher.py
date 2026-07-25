"""
News Fetcher — オンデマンドニュース取得（定期RSS廃止）

【ポリシー】
- 定期巡回は行わない。ユーザーが「ニュースある？」と聞いたタイミングで取得
- 1次情報 (PR Newswire, BusinessWire, AP News) を優先
- RSS取得結果が少ない場合はBraveで補完
- 結果はcache_managerで30分キャッシュ
"""
import re
import feedparser
from typing import Optional
from app.utils.logger import get_logger
from app.core.search.router import fetch_url

logger = get_logger(__name__)

# 1次情報＆世界・国内株式市場最速速報RSS（ペイウォールなし・全文取得可能）
ON_DEMAND_FEEDS = [
    # --- 🏢 【最速0秒・真の1次情報】企業公式開示・グローバル3大プレスリリース網羅 ---
    {"name": "SEC EDGAR 8-K (米国証券取引委員会 公式適時開示)", "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom"},
    {"name": "PR Newswire (公式発表)", "url": "https://www.prnewswire.com/rss/news-releases-list.rss"},
    {"name": "BusinessWire (公式発表)", "url": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFdX"},
    {"name": "GlobeNewswire (公式発表)", "url": "https://www.globenewswire.com/NewsRoom/Rss"},
    # --- 🇺🇸 米国ウォール街速報・プロ投資家向け最速ヘッドライン ---
    {"name": "Seeking Alpha Market Currents (米株最速速報)", "url": "https://seekingalpha.com/market_currents.xml"},
    {"name": "WSJ Markets (ウォール・ストリート・ジャーナル)", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"},
    {"name": "CNBC Market News", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"},
    {"name": "CNBC Investing / Stocks", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"},
    {"name": "MarketWatch Top Stories", "url": "http://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "MarketWatch Market Pulse", "url": "http://feeds.marketwatch.com/marketwatch/marketpulse/"},
    {"name": "Yahoo Finance Top News", "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "Investing.com Stock Market News", "url": "https://www.investing.com/rss/news_25.rss"},
    # --- 🇯🇵＆🇰🇷 アジア株コア速報 (東京・韓国半導体震源) ---
    {"name": "Yahoo Japan 経済・市況", "url": "https://news.yahoo.co.jp/rss/topics/business.xml"},
    {"name": "Yahoo Japan IT/テック", "url": "https://news.yahoo.co.jp/rss/topics/it.xml"},
    {"name": "Yonhap News Economy (韓国聯合ニュース 経済速報)", "url": "https://www.yna.co.kr/rss/economy.xml"},
    # --- 📡 グローバル通信社＆主要テックメディア ---
    {"name": "AP News", "url": "https://rsshub.app/apnews/topics/apf-topnews"},
    {"name": "Reuters", "url": "https://www.reutersagency.com/feed/"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
]

# 新しいニュースを確保するための最小件数
MIN_NEWS_COUNT = 15


def normalize_entry(entry, source_name: str) -> Optional[dict]:
    """feedparserのエントリーを正規化"""
    try:
        return {
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", entry.get("updated", "")),
            "source": source_name,
            "summary": entry.get("summary", ""),
        }
    except Exception:
        return None


async def fetch_rss_on_demand(feeds: list[dict] = None) -> list[dict]:
    """
    オンデマンドでRSSを取得。定期巡回はしない。
    
    Args:
        feeds: 取得するフィード一覧。Noneの場合はデフォルト
    Returns:
        正規化されたニュースアイテムのリスト
    """
    if feeds is None:
        feeds = ON_DEMAND_FEEDS
    
    all_items = []
    logger.info(f"📡 オンデマンドRSS取得開始: {len(feeds)}フィード")
    
    from app.core.search.providers.http_client import get_http_client
    import bs4

    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            if parsed.bozo and not parsed.entries:
                logger.warning(f"⚠️ RSSパース失敗: {feed['name']} - {parsed.bozo_exception}。BeautifulSoupでの強制抽出を試みます")
                try:
                    client = get_http_client()
                    resp = await client.get(feed["url"], timeout=10)
                    # XMLパーサーで試行
                    soup = bs4.BeautifulSoup(resp.content, "xml")
                    items = soup.find_all(['item', 'entry'])
                    if not items:
                        # HTMLパーサーで再試行（タグのネストが壊れている場合用）
                        soup = bs4.BeautifulSoup(resp.content, "html.parser")
                        items = soup.find_all(['item', 'entry'])
                    
                    added = 0
                    for item in items:
                        title_tag = item.find('title')
                        link_tag = item.find('link')
                        # linkは <link>URL</link> と <link href="URL"/> の両方に対応
                        link_val = link_tag.get('href') if link_tag and link_tag.has_attr('href') else (link_tag.text if link_tag else "")
                        
                        summary_tag = item.find('description') or item.find('summary') or item.find('content')
                        pub_tag = item.find('pubDate') or item.find('published') or item.find('updated')
                        
                        if title_tag and link_val:
                            normalized = {
                                "title": title_tag.text.strip(),
                                "url": link_val.strip(),
                                "published": pub_tag.text.strip() if pub_tag else "",
                                "source": feed["name"],
                                "summary": summary_tag.text.strip() if summary_tag else "",
                            }
                            all_items.append(normalized)
                            added += 1
                    
                    if added > 0:
                        logger.info(f"✅ {feed['name']}: {added}件 (BeautifulSoupフォールバック)")
                        continue
                    else:
                        logger.warning(f"⚠️ フォールバック抽出でも記事が見つかりませんでした: {feed['name']}")
                        continue
                except Exception as fb_e:
                    logger.warning(f"⚠️ フォールバック処理エラー: {feed['name']} - {fb_e}")
                    continue
            
            logger.info(f"✅ {feed['name']}: {len(parsed.entries)}件")
            
            for entry in parsed.entries:
                normalized = normalize_entry(entry, feed["name"])
                if normalized and normalized.get("title") and normalized.get("url"):
                    all_items.append(normalized)
                    
        except Exception as e:
            logger.error(f"❌ RSS取得エラー {feed['name']}: {e}")
    
    logger.info(f"📊 オンデマンドRSS取得完了: 合計{len(all_items)}件")
    return all_items


async def fetch_primary_news(query: str = "") -> list[dict]:
    """
    1次情報を優先してニュースを取得。
    
    フロー:
    1. 主要RSSをその場で取得
    2. 日本市場・国内株クエリ時は海外テック系RSSノイズを除外し、国内市況を検索
    3. キーワードがあればBraveで補完検索
    4. 結果を結合して返す
    """
    is_jp_or_market = any(
        kw in query
        for kw in ["日本", "日経", "東京", "東証", "TOPIX", "株", "為替", "円", "国内", "市場"]
    )
    is_finance = any(
        kw in query
        for kw in ["銘柄", "投資", "ETF", "決算", "半導体", "インフレ", "経済", "FRB", "金利", "雇用", "相場"]
    )

    if query and not (is_jp_or_market or is_finance or "ニュース" in query or "news" in query.lower()):
        # 経済・市場以外の一般的なクエリ（例：酒、トレンドなど）の場合は、
        # 証券系のRSSを叩かずに空配列から開始し、後続のBraveフォールバックへ委譲する
        results = []
    else:
        results = await fetch_rss_on_demand()
    
    if is_jp_or_market and results:
        # 日本市場や株価に関する質問の場合、無関係な海外テック系RSS（Hacker News等）を除外する
        results = [
            r for r in results
            if r.get("source") not in ["Hacker News", "MIT Technology Review", "Ars Technica", "TechCrunch"]
        ]

    # キーワードがあればBraveで補完検索
    if query:
        from app.core.search import web_search
        if is_jp_or_market:
            site_query = f"{query} 日経平均 OR 株価 OR 東京株式市場 OR 終値 OR ニュース"
        else:
            site_query = f"site:prnewswire.com OR site:businesswire.com OR site:apnews.com {query}"
        brave_text, brave_sources = await web_search(site_query, providers=["brave"])
        
        if brave_sources:
            # 重複チェック（URLベース）
            existing_urls = {item["url"] for item in results if item.get("url")}
            for src in brave_sources:
                if src.get("url") not in existing_urls:
                    results.append({
                        "title": src.get("title", ""),
                        "url": src.get("url", ""),
                        "published": "",
                        "source": "PRIMARY (Brave JP)" if is_jp_or_market else "PRIMARY (Brave)",
                        "summary": src.get("snippet", ""),
                    })
    
    # RSS結果が少ない場合、Braveで一般ニュース検索して補完
    if len(results) < MIN_NEWS_COUNT:
        logger.info(f"⚠️ RSS取得が{len(results)}件と少ないため、Braveで補完検索を実行")
        try:
            from app.core.search import web_search
            fallback_query = (
                f"{query} 日本市場 株価 市況 最新ニュース"
                if is_jp_or_market
                else (query if query else "latest breaking news 2026")
            )
            brave_text, brave_sources = await web_search(fallback_query, providers=["brave"])
            
            if brave_sources:
                existing_urls = {item["url"] for item in results if item.get("url")}
                added = 0
                for src in brave_sources:
                    if src.get("url") and src.get("url") not in existing_urls:
                        results.append({
                            "title": src.get("title", ""),
                            "url": src.get("url", ""),
                            "published": src.get("published", ""),
                            "source": "NEWS (Brave)",
                            "summary": src.get("snippet", ""),
                        })
                        existing_urls.add(src.get("url"))
                        added += 1
                logger.info(f"✅ Brave補完: {added}件追加")
        except Exception as e:
            logger.warning(f"⚠️ Brave補完検索エラー: {e}")
    
    logger.info(f"📊 最終ニュース件数: {len(results)}件")
    return results