import re

file_path = 'd:/program/chat/backend/app/routers/settings.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

new_endpoint = """
from app.core.cache_manager import get_cache_stats

@router.get("/stats")
async def get_stats():
    \"\"\"キャッシュ統計情報を取得\"\"\"
    return await get_cache_stats()
"""

if "@router.get(\"/stats\")" not in content:
    content += new_endpoint
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("settings.py patched with /stats endpoint.")
else:
    print("/stats endpoint already exists.")
