import os
from dotenv import load_dotenv

load_dotenv()
print("API KEY:", os.environ.get("MARKETSTACK_API_KEY", "MISSING")[:5] + "***")

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.core.tools.finance import fetch_hot_stocks
print("Testing fetch_hot_stocks...")
res = fetch_hot_stocks()
print("Result:")
print(res)
