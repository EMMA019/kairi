import aiosqlite
import json
from datetime import datetime
from app.utils.logger import get_logger
import os

logger = get_logger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "news.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guid TEXT,
                title TEXT,
                url TEXT,
                published TEXT,
                source TEXT,
                summary TEXT,
                category TEXT,
                importance INTEGER,
                sentiment TEXT,
                stock_codes TEXT,
                tags TEXT,
                body_text TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Duplicate checks will use these indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_news_guid ON news(guid)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_news_url ON news(url)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_news_title ON news(title)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published)")
        
        # 🧹 古い定期RSSデータをクリア（オンデマンド化に伴い）
        await db.execute("DELETE FROM news")
        
        await db.commit()
    logger.info("News DB initialized (old RSS data cleared).")

async def is_duplicate(db: aiosqlite.Connection, item: dict) -> bool:
    """
    重複チェック (GUID -> URL -> Titleの順)
    """
    guid = item.get("guid")
    url = item.get("url")
    title = item.get("title")

    if guid:
        cursor = await db.execute("SELECT id FROM news WHERE guid = ?", (guid,))
        if await cursor.fetchone():
            return True

    if url:
        cursor = await db.execute("SELECT id FROM news WHERE url = ?", (url,))
        if await cursor.fetchone():
            return True

    if title:
        cursor = await db.execute("SELECT id FROM news WHERE title = ?", (title,))
        if await cursor.fetchone():
            return True

    return False

async def save_news(items: list[dict]):
    """
    ニュースのリストをDBに保存。重複はスキップ。
    """
    inserted = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            if await is_duplicate(db, item):
                continue
            
            # Serialize lists/dicts to JSON strings
            stock_codes = json.dumps(item.get("stock_codes", []), ensure_ascii=False)
            tags = json.dumps(item.get("tags", []), ensure_ascii=False)
            
            await db.execute("""
                INSERT INTO news (
                    guid, title, url, published, source, summary,
                    category, importance, sentiment, stock_codes, tags, body_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("guid"),
                item.get("title"),
                item.get("url"),
                item.get("published"),
                item.get("source"),
                item.get("summary"),
                item.get("category"),
                item.get("importance"),
                item.get("sentiment"),
                stock_codes,
                tags,
                item.get("body_text")
            ))
            inserted += 1
        await db.commit()
    return inserted

async def update_news_analysis(news_id: int, analysis: dict):
    """
    AIによる分析結果でニュースを更新する。
    """
    stock_codes = json.dumps(analysis.get("stocks", []), ensure_ascii=False)
    tags = json.dumps(analysis.get("tags", []), ensure_ascii=False)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE news SET
                importance = ?,
                sentiment = ?,
                category = ?,
                stock_codes = ?,
                tags = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            analysis.get("importance"),
            analysis.get("sentiment"),
            analysis.get("sector"),
            stock_codes,
            tags,
            news_id
        ))
        await db.commit()

async def update_news_body(news_id: int, body_text: str):
    """
    取得した本文テキストを保存する
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE news SET
                body_text = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (body_text, news_id))
        await db.commit()

async def get_unprocessed_news() -> list[dict]:
    """
    まだ分析されていない(importanceがNULL)ニュースを取得する
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM news WHERE importance IS NULL ORDER BY published DESC LIMIT 50")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def search_news(query: str = None, limit: int = 15) -> list[dict]:
    """
    ニュースを検索する (チャットUIからの呼び出し用)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # 簡易的なSQL検索。必要に応じて全文検索(FTS)やベクトル検索に拡張可能。
        sql = "SELECT * FROM news WHERE importance IS NOT NULL"
        params = []
        
        if query:
            import re
            # 日付関連キーワードを抽出（年・月・日・特定日付）して別途保持
            date_keywords = []
            date_extracted = set()
            # 明示的な日付パターン: "July 2 2026", "7月2日", "2026年7月" etc.
            date_patterns = re.findall(r'(\d{4}年?\s*\d{1,2}月?\s*\d{1,2}日?|july|august|september|october|november|december|january|february|march|april|may|june|202[0-9])', query, flags=re.IGNORECASE)
            for dp in date_patterns:
                dp_lower = dp.lower().strip()
                if dp_lower not in date_extracted:
                    date_extracted.add(dp_lower)
                    date_keywords.append(dp_lower)
            
            # 一般的な検索ノイズのみを除去（日付・ニュース関連語は除去しない！）
            clean_q = re.sub(r'(教えて|気になる|について|ください)', '', query, flags=re.IGNORECASE).strip()
            keywords = [w for w in re.split(r'\s+', clean_q) if len(w) >= 2]
            
            if not keywords and query.strip():
                keywords = [query.strip()]
            
            # 抽出した日付キーワードをkeywordsの先頭に追加（優先度を上げる）
            for dk in date_keywords:
                if dk not in keywords:
                    keywords.insert(0, dk)
                
            if keywords:
                # 複数キーワードのいずれかがタイトル・要約・タグ・証券コードに含まれるか精密検索
                conditions = []
                for kw in keywords:
                    conditions.append("(title LIKE ? OR summary LIKE ? OR tags LIKE ? OR stock_codes LIKE ?)")
                    like_kw = f"%{kw}%"
                    params.extend([like_kw, like_kw, like_kw, like_kw])
                sql += " AND (" + " OR ".join(conditions) + ")"
            
            # 日付キーワードが含まれる場合はpublishedの日付範囲フィルタを追加
            if date_keywords:
                year_match = re.search(r'(202[0-9])年?', query)
                year = year_match.group(1) if year_match else None
                
                # Check for English month
                month_map = {
                    'january': '01', 'february': '02', 'march': '03', 'april': '04',
                    'may': '05', 'june': '06', 'july': '07', 'august': '08',
                    'september': '09', 'october': '10', 'november': '11', 'december': '12'
                }
                eng_month = None
                for m_name, m_num in month_map.items():
                    if m_name in query.lower():
                        eng_month = m_num
                        break
                
                # Check for Japanese month
                jp_month_match = re.search(r'(1?[0-9])月', query)
                jp_month = jp_month_match.group(1).zfill(2) if jp_month_match else None
                
                month = eng_month or jp_month
                
                # Check for day (1-2 digits not surrounded by other digits)
                day_match = re.search(r'(?<!\d)(\d{1,2})(?:日)?(?!\d)', query)
                day = day_match.group(1).zfill(2) if day_match else None
                
                if year and month and day:
                    from datetime import datetime, timedelta
                    try:
                        target_date = datetime(int(year), int(month), int(day))
                        start_date = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
                        end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
                        sql += f" AND published >= ? AND published <= ?"
                        params.extend([start_date, end_date])
                    except ValueError:
                        # Invalid day, fallback to month
                        sql += f" AND published LIKE ?"
                        params.append(f"{year}-{month}%")
                elif year and month:
                    sql += f" AND published LIKE ?"
                    params.append(f"{year}-{month}%")
                elif year:
                    sql += f" AND published LIKE ?"
                    params.append(f"{year}%")
                elif month:
                    sql += f" AND (published LIKE ? OR published LIKE ?)"
                    params.extend([f"2026-{month}%", f"2025-{month}%"])
            
        sql += " ORDER BY published DESC, importance DESC LIMIT ?"
        params.append(limit)
        
        cursor = await db.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        
        # 【重要改修】：個別キーワード指定時にヒットしなかった場合、無関係な総合ニュースをランダムに返すフォールバックを完全撤廃！
        # これにより0件が正常に返り、router.pyがBrave Web検索等へフォールバックして本物の個別銘柄ニュース（ALNY等）を獲得できます。
        if not rows and query:
            if query.lower().strip() in ["latest", "news", "最新", "ニュース", "最新ニュース", "ヘッドライン"]:
                cursor = await db.execute("SELECT * FROM news WHERE importance IS NOT NULL ORDER BY published DESC LIMIT ?", (limit,))
                rows = await cursor.fetchall()
            else:
                return []
        
        results = []
        for row in rows:
            r = dict(row)
            try:
                r["stock_codes"] = json.loads(r["stock_codes"]) if r["stock_codes"] else []
                r["tags"] = json.loads(r["tags"]) if r["tags"] else []
            except:
                pass
            results.append(r)
        return results
