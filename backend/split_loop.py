import os
import re

old_path = r"d:\program\chat\backend\app\core\auto_execution_loop\_old.py"
base_dir = r"d:\program\chat\backend\app\core\auto_execution_loop"

with open(old_path, "r", encoding="utf-8") as f:
    content = f.read()

# Common imports
common_imports = """import json
import re
import asyncio
import uuid
import time
from typing import AsyncGenerator, Optional
from datetime import datetime
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)
"""

# Extract heuristics
heuristics_match = re.search(r'(def _detect_test_failure.*?)(?=async def _smart_compress_loop_history)', content, re.DOTALL)
heuristics_content = heuristics_match.group(1) if heuristics_match else ""

with open(os.path.join(base_dir, "heuristics.py"), "w", encoding="utf-8") as f:
    f.write(common_imports + "\n" + heuristics_content)

# Extract compression
compression_match = re.search(r'(async def _smart_compress_loop_history.*?)(?=async def auto_execute_with_retry)', content, re.DOTALL)
compression_content = compression_match.group(1) if compression_match else ""
compression_imports = common_imports + """from app.core.llm_client import call_model\nfrom app.routers.settings import get_settings\n"""
with open(os.path.join(base_dir, "compression.py"), "w", encoding="utf-8") as f:
    f.write(compression_imports + "\n" + compression_content)

# Extract supervisor
supervisor_match = re.search(r'(async def _analyze_with_supervisor.*)', content, re.DOTALL)
supervisor_content = supervisor_match.group(1) if supervisor_match else ""
supervisor_imports = common_imports + """from app.core.llm_client import call_model\nfrom app.routers.settings import get_settings\nfrom app.core.supervisor import get_supervisor_system_prompt\nfrom app.core.tools.manager import get_tool_descriptions\n"""
with open(os.path.join(base_dir, "supervisor.py"), "w", encoding="utf-8") as f:
    f.write(supervisor_imports + "\n" + supervisor_content)

# Extract loop (auto_execute_with_retry)
loop_match = re.search(r'(async def auto_execute_with_retry.*?)(?=async def _analyze_with_supervisor)', content, re.DOTALL)
loop_content = loop_match.group(1) if loop_match else ""

loop_imports = common_imports + """
from app.core.tools.handler import execute_tool
from app.core.tools.parser import parse_tool_calls
from app.core.llm_client import stream_model
from app.routers.settings import get_settings
from app.core.fact_filters import validate_and_refine_facts

from .heuristics import _detect_test_failure, _detect_error, _detect_success
from .compression import _smart_compress_loop_history
from .supervisor import _analyze_with_supervisor
"""
with open(os.path.join(base_dir, "loop.py"), "w", encoding="utf-8") as f:
    f.write(loop_imports + "\n" + loop_content)

# Create __init__.py
init_content = """from .loop import auto_execute_with_retry

__all__ = ["auto_execute_with_retry"]
"""
with open(os.path.join(base_dir, "__init__.py"), "w", encoding="utf-8") as f:
    f.write(init_content)

print("auto_execution_loop split successfully.")
