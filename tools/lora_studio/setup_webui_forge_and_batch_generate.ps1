# ==============================================================================
# Stable Diffusion WebUI Forge Setup and Batch Generator
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$ForgeDir = Join-Path $ScriptDir "sd-webui-forge"
$LoraModelDir = Join-Path $ForgeDir "models\Lora"
$OutputGalleryDir = Join-Path $ProjectRoot "img"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " SD WebUI Forge Setup and Batch Stock Generator Studio" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

if (-not (Test-Path $ForgeDir)) {
    Write-Host "`n[1/3] Downloading SD WebUI Forge from GitHub..." -ForegroundColor Yellow
    git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git $ForgeDir
} else {
    Write-Host "`n[1/3] SD WebUI Forge already exists at: $ForgeDir" -ForegroundColor Green
}

Write-Host "`n[2/3] Checking trained LoRA models..." -ForegroundColor Yellow
if (-not (Test-Path $LoraModelDir)) { New-Item -ItemType Directory -Force -Path $LoraModelDir | Out-Null }
$TrainedLora = Join-Path $ScriptDir "output\kairi_v1.safetensors"
if (Test-Path $TrainedLora) {
    Copy-Item $TrainedLora -Destination $LoraModelDir -Force
    Write-Host "  -> Placed kairi_v1.safetensors into Forge Lora folder!" -ForegroundColor Green
} else {
    Write-Host "  -> Note: kairi_v1.safetensors not found in output yet. Train first with setup_kohya_and_train.ps1." -ForegroundColor Gray
}

$BatchGenScript = Join-Path $ScriptDir "run_batch_generator.py"
$BatchPython = @"
import urllib.request
import json
import base64
import os
import time

API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUTPUT_DIR = r"$OutputGalleryDir"
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
        "width": 512,
        "height": 512,
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
    except Exception as e:
        print(f"  -> Error: {e}")
print("Batch generation complete!")
"@
Set-Content -Path $BatchGenScript -Value $BatchPython -Encoding UTF8
Write-Host "`n[3/3] Created batch generation script: $BatchGenScript" -ForegroundColor Green
