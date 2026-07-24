import os
import re

old_path = r"d:\program\chat\backend\app\core\prompt_builder\_old.py"
base_dir = r"d:\program\chat\backend\app\core\prompt_builder"

with open(old_path, "r", encoding="utf-8") as f:
    content = f.read()

# Define common imports
common_imports = """import json
import re
from datetime import datetime
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
"""

# Extract loaders
loaders_match = re.search(r'(def load_prompt.*?)(?=HIGH_CONFIDENCE_THRESHOLD)', content, re.DOTALL)
loaders_content = loaders_match.group(1) if loaders_match else ""

with open(os.path.join(base_dir, "loader.py"), "w", encoding="utf-8") as f:
    f.write(common_imports + "\n" + loaders_content)

# Extract entity_resolution
er_match = re.search(r'(HIGH_CONFIDENCE_THRESHOLD.*?)(?=def build_system_instruction)', content, re.DOTALL)
er_content = er_match.group(1) if er_match else ""

with open(os.path.join(base_dir, "entity_resolution.py"), "w", encoding="utf-8") as f:
    f.write(common_imports + "\n" + er_content)

# Extract builder
builder_match = re.search(r'(def build_system_instruction.*)', content, re.DOTALL)
builder_content = builder_match.group(1) if builder_match else ""

builder_imports = common_imports + """
from .loader import load_prompt, load_active_skills, load_knowledge_summary
from .entity_resolution import fuzzy_match_entities, resolve_zero_anaphora, build_entity_registry_context
"""

with open(os.path.join(base_dir, "builder.py"), "w", encoding="utf-8") as f:
    f.write(builder_imports + "\n" + builder_content)

# Create __init__.py
init_content = """from .builder import build_system_instruction, build_search_retry_instruction

__all__ = ["build_system_instruction", "build_search_retry_instruction"]
"""
with open(os.path.join(base_dir, "__init__.py"), "w", encoding="utf-8") as f:
    f.write(init_content)

print("prompt_builder split successfully.")
