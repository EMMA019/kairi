import os

file_path = r"d:\program\chat\backend\app\core\auto_execution_loop\loop.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("from app.core.tools.handler import execute_tool", "from app.core.tools.handler import ToolHandler")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("loop.py import fixed.")
