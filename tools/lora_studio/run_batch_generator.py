import urllib.request
import urllib.error
import json
import base64
import os
import time

#[cite: 1]
API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUTPUT_DIR = r"D:\program\chat\img"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 提供された6つの新しいタグリストを反映しました。
prompts = [
    "<lora:kairi_v1:1.0>, kairi, 1girl, breasts, looking at viewer, skirt, long sleeves, ribbon, jewelry, medium breasts, standing, collarbone, full body, hair ribbon, braid, pleated skirt, earrings, outdoors, multiple boys, shoes, solo focus, socks, bag, nail polish, blurry, two-tone hair, sweater, red ribbon, blue skirt, kneehighs, night, depth of field, blurry background, pov, backpack, ground vehicle, loafers, building, night sky, motor vehicle, pink nails, ribbed sweater, city, sign, car, road, street, pink sweater, crosswalk", #[cite: 2]
    "<lora:kairi_v1:1.0>, kairi, 1girl, breasts, looking at viewer, blush, smile, bow, ribbon, cleavage, bare shoulders, medium breasts, closed mouth, collarbone, swimsuit, hair ribbon, upper body, flower, hair bow, bikini, outdoors, frills, water, red bow, tree, bird, ocean, plant, red bikini, sunset, palm tree", #[cite: 3]
    "<lora:kairi_v1:1.0>, kairi, 1girl, looking at viewer, blush, skirt, shirt, long sleeves, bow, ribbon, sitting, closed mouth, school uniform, jacket, hair ribbon, white shirt, braid, indoors, bowtie, red bow, book, plaid, red skirt, plaid skirt, chair, blazer, desk, wooden floor, classroom, school desk, chalkboard, school chair, school", #[cite: 4]
    "<lora:kairi_v1:1.0>, kairi, 1girl, breasts, looking at viewer, blush, bow, ribbon, cleavage, bare shoulders, medium breasts, collarbone, swimsuit, hair ribbon, upper body, flower, hair bow, bikini, outdoors, frills, teeth, tears, water, tree, bird, ocean, crying, plant, clenched teeth, crying with eyes open, sunset, palm tree, streaming tears", #[cite: 5]
    "<lora:kairi_v1:1.0>, kairi, 1girl, looking at viewer, blush, smile, long sleeves, ribbon, jewelry, closed mouth, jacket, hair ribbon, upper body, braid, earrings, outdoors, hand up, blurry, from side, red ribbon, fur trim, night, depth of field, blurry background, denim, blue jacket, ground vehicle, building, night sky, motor vehicle, pocket, city, car, stud earrings, road, street, city lights, denim jacket", #[cite: 6]
    "<lora:kairi_v1:1.0>, kairi, 1girl, breasts, looking at viewer, blush, bow, ribbon, cleavage, bare shoulders, medium breasts, closed mouth, collarbone, swimsuit, hair ribbon, upper body, hair bow, bikini, outdoors, frills, water, red bow, tree, v-shaped eyebrows, bird, ocean, frown, plant, fish, red bikini, sunset, palm tree" #[cite: 7]
]

print("[Kairi Batch Studio] Starting batch image generation...") #[cite: 1]
for idx, p in enumerate(prompts * 10): #[cite: 1]
    payload = {
        "prompt": p,
        "negative_prompt": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry", #[cite: 1]
        "steps": 25, #[cite: 1]
        "width": 832, #[cite: 1]
        "height": 1216, #[cite: 1]
        "cfg_scale": 7.0, #[cite: 1]
        "sampler_name": "Euler a" #[cite: 1]
    }
    try:
        req = urllib.request.Request(API_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}) #[cite: 1]
        with urllib.request.urlopen(req) as response: #[cite: 1]
            res_data = json.loads(response.read().decode('utf-8')) #[cite: 1]
            for img_b64 in res_data.get('images', []): #[cite: 1]
                filename = f"kairi_stock_{int(time.time())}_{idx}.png" #[cite: 1]
                filepath = os.path.join(OUTPUT_DIR, filename) #[cite: 1]
                with open(filepath, "wb") as f: #[cite: 1]
                    f.write(base64.b64decode(img_b64)) #[cite: 1]
                print(f"  -> Added new stock image: {filepath}") #[cite: 1]
    except urllib.error.HTTPError as e: #[cite: 1]
        print(f"  -> Error HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}") #[cite: 1]
    except Exception as e: #[cite: 1]
        print(f"  -> Error: {e}") #[cite: 1]
print("Batch generation complete!") #[cite: 1]