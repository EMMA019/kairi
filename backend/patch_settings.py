import re

with open('d:/program/chat/backend/app/routers/settings.py', 'r', encoding='utf-8') as f:
    content = f.read()

if "from app.core.usage_tracker" not in content:
    content = content.replace(
        "from fastapi import APIRouter",
        "from fastapi import APIRouter\nfrom app.core.usage_tracker import get_daily_usage"
    )

new_endpoint = """
@router.get("/usage")
async def get_usage():
    \"\"\"現在のトークン使用量と概算コストを取得\"\"\"
    return get_daily_usage()
"""

if "@router.get(\"/usage\")" not in content:
    content += new_endpoint

with open('d:/program/chat/backend/app/routers/settings.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("settings.py patched successfully.")
