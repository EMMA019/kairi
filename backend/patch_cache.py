import os

file_path = 'd:/program/chat/backend/app/core/cache_manager.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_func = """
async def get_cache_stats() -> dict:
    \"\"\"キャッシュの統計情報（ヒット率など）を取得\"\"\"
    stats = {}
    try:
        async with aiosqlite.connect(CACHE_DB_PATH) as db:
            for table in ["llm_cache", "search_cache", "command_cache"]:
                try:
                    async with db.execute(f"SELECT COUNT(*), SUM(hit_count) FROM {table}") as cursor:
                        row = await cursor.fetchone()
                        count = row[0] if row and row[0] is not None else 0
                        hits = row[1] if row and row[1] is not None else 0
                        # hit_count DEFAULT 1 なので、実際には 1 回目は生成。キャッシュヒットは hit_count - 1
                        actual_hits = max(0, hits - count)
                        stats[table] = {
                            "entries": count,
                            "hits": actual_hits
                        }
                except Exception:
                    stats[table] = {"entries": 0, "hits": 0}
                    
        total_entries = sum(s["entries"] for s in stats.values())
        total_hits = sum(s["hits"] for s in stats.values())
        stats["total"] = {
            "entries": total_entries,
            "hits": total_hits
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
    return stats
"""

if "def get_cache_stats" not in content:
    content += "\n" + new_func
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("cache_manager.py patched with get_cache_stats.")
else:
    print("get_cache_stats already exists.")
