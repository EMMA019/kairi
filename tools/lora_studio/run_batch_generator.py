import urllib.request
import urllib.error
import json
import base64
import os
import time

API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUTPUT_DIR = r"D:\program\chat\img"
os.makedirs(OUTPUT_DIR, exist_ok=True)

prompts = [
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, energetic big smile, gyaru style, cute casual fashion, cafe background, masterpiece, best quality, ultra-detailed",
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, gentle smile, white hoodie, street background, masterpiece, best quality, ultra-detailed",
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, winking, peace sign, selfie pose, bedroom background, masterpiece, best quality, ultra-detailed"
]

print("[Kairi Batch Studio] Starting batch image generation...")
for idx, p in enumerate(prompts * 10):
    payload = {
        "prompt": p,
        "negative_prompt": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
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
            for img_b64 in res_data.get('images', []):
                filename = f"kairi_stock_{int(time.time())}_{idx}.png"
                filepath = os.path.join(OUTPUT_DIR, filename)
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(img_b64))
                print(f"  -> Added new stock image: {filepath}")
    except urllib.error.HTTPError as e:
        print(f"  -> Error HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"  -> Error: {e}")
print("Batch generation complete!")
