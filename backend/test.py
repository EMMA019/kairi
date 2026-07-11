import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("MARKETSTACK_API_KEY")
if not API_KEY:
    print("❌ APIキーが設定されていません")
    exit()

BASE_URL = "http://api.marketstack.com/v1"

# AAPLの最新終値を取得
params = {
    "access_key": API_KEY,
    "symbols": "AAPL"
}

try:
    response = requests.get(f"{BASE_URL}/eod/latest", params=params, timeout=10)
    data = response.json()
    
    if "data" in data and data["data"]:
        latest = data["data"][0]
        print(f"✅ AAPL 最新終値: ${latest['close']:.2f} ({latest['date']})")
        print(f"   - 高値: ${latest['high']:.2f}")
        print(f"   - 安値: ${latest['low']:.2f}")
    else:
        print("❌ データが取得できませんでした:", data)
except Exception as e:
    print(f"❌ エラー: {e}")