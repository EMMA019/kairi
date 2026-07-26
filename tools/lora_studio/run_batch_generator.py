import urllib.request
import urllib.error
import json
import base64
import os
import time
import random

API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUTPUT_DIR = r"D:\program\chat\img\stock"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 髪・瞳を明示してバッチ間のドリフトを抑える（夕焼けで瞳がアンバー化する等を軽減）
BASE_TAGS = (
    "<lora:kairi_v1:1.0>, kairi, 1girl, "
    "short magenta bob hair, pink eyes, earrings, "
    "masterpiece, best quality, ultra-detailed"
)
NEG_PROMPT = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
    "signature, watermark, username, blurry, two-tone hair, "
    "blonde hair, brown hair, black hair, blue eyes, green eyes, amber eyes, yellow eyes"
)

# シチュエーションごとのグループ化（TPOをわきまえる）
scenarios = [
    {
        "theme": "casual",
        "clothing": ["cute casual fashion", "white hoodie", "ribbed sweater", "denim jacket", "pink sweater"],
        "backgrounds": ["cafe background", "street background", "city", "night lights", "crosswalk", "building"]
    },
    {
        "theme": "school",
        "clothing": ["school uniform", "white shirt, bowtie", "blazer, plaid skirt", "jacket, red bow"],
        "backgrounds": ["indoors, classroom", "school desk", "chalkboard", "school chair", "wooden floor"]
    },
    {
        "theme": "beach",
        "clothing": ["swimsuit", "bikini", "red bikini", "frills"],
        "backgrounds": ["outdoors, ocean", "sunset, palm tree", "water, tree, bird"]
    },
    {
        "theme": "room",
        "clothing": ["cute casual fashion", "white hoodie", "sweater"],
        "backgrounds": ["bedroom background", "indoors"]
    },
    # ご要望にお応えして、低確率で出現する「TPO無視」のハプニング枠も追加しておきましたｗ
    {
        "theme": "happening",
        "clothing": ["bikini", "swimsuit", "red bikini"],
        "backgrounds": ["cafe background", "classroom", "street background", "crosswalk", "school desk"]
    }
]

# テーマごとの出現確率の重み付け（casual:30%, school:30%, beach:15%, room:15%, happening:10%）
scenario_weights = [0.30, 0.30, 0.15, 0.15, 0.10]

# 共通要素
expressions = ["energetic big smile", "gentle smile", "winking", "blush, smile", "closed mouth", "pout"]
poses_details = ["peace sign", "selfie pose", "from side", "hand up", "looking at viewer", "braid", "long sleeves", "earrings"]

print("[Kairi Stock Generator v3] Starting massive stock generation...")
TOTAL_IMAGES = 60

for idx in range(TOTAL_IMAGES):
    # テーマを重み付けでランダム選択
    scenario = random.choices(scenarios, weights=scenario_weights, k=1)[0]
    
    theme_name = scenario["theme"]
    clothing = random.choice(scenario["clothing"])
    background = random.choice(scenario["backgrounds"])
    
    expression = random.choice(expressions)
    pose_detail = random.choice(poses_details)

    # プロンプト組み立て
    p = f"{BASE_TAGS}, {expression}, {clothing}, {background}, {pose_detail}"

    payload = {
        "prompt": p,
        "negative_prompt": NEG_PROMPT,
        "steps": 25,
        "width": 832,
        "height": 1216,
        "cfg_scale": 7.0,
        "sampler_name": "Euler a"
    }

    try:
        req = urllib.request.Request(API_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            for i, img_b64 in enumerate(res_data.get('images', [])):
                # ファイル名にテーマを含めることでチャットAIが検索しやすくなる
                filename = f"kairi_{theme_name}_{int(time.time())}_{idx}.png"
                filepath = os.path.join(OUTPUT_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(img_b64))
                print(f"  -> Added {theme_name} stock: {filepath}")
    except urllib.error.HTTPError as e:
        print(f"  -> Error HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"  -> Error: {e}")

print("Massive stock generation complete!")
