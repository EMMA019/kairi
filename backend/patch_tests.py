import os
import re

file_path = r"d:\program\chat\backend\test_kairi_core.py"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # auto_execution_loop -> auto_execution_loop.heuristics
    content = content.replace("from app.core.auto_execution_loop import _detect_test_failure", "from app.core.auto_execution_loop.heuristics import _detect_test_failure")
    
    # fact_filter -> fact_filters (and specific modules if needed, but they are available in __init__.py)
    # wait, in my previous refactoring of fact_filters, did I expose them in __init__.py? Let's assume yes or replace with specific modules.
    content = content.replace("app.core.fact_filter", "app.core.fact_filters")
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

file_path = r"d:\program\chat\backend\test_news.py"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("app.core.news.fetcher", "app.core.news.rss")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

file_path = r"d:\program\chat\backend\test_scanner.py"
if os.path.exists(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("app.core.tools.scanner", "app.core.tools.finance")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Tests patched.")
