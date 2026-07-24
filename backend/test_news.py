import asyncio
import os
from dotenv import load_dotenv

# Load env vars first
load_dotenv()

from app.core.news.database import init_db, get_unprocessed_news, search_news
from app.core.news.rss import fetch_rss_feeds

async def main():
    print("=== News Pipeline Test ===")
    
    # 1. DB初期化
    print("Initializing DB...")
    await init_db()
    
    # 2. テスト用にフィードを1つだけ取得する
    test_feeds = [
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"}
    ]
    
    print("\nFetching RSS feeds (Yahoo Finance only)...")
    await fetch_rss_feeds(test_feeds)
    
    # 3. 未処理が残っていないか確認
    unprocessed = await get_unprocessed_news()
    print(f"\nUnprocessed news remaining: {len(unprocessed)}")
    
    # 4. 検索テスト
    print("\nSearching DB for news...")
    results = await search_news(limit=3)
    for r in results:
        print("-" * 40)
        print(f"[{r['source']}] {r['title']}")
        print(f"Date: {r['published']}")
        print(f"Importance: {r['importance']} | Sentiment: {r['sentiment']}")
        print(f"Tags: {r['tags']}")
        print(f"Stocks: {r['stock_codes']}")
        
    print("\n=== Test Completed ===")

if __name__ == "__main__":
    asyncio.run(main())
