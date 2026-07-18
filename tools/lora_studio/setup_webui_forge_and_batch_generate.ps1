# ==============================================================================
# Stable Diffusion WebUI Forge ワンクリック構築 ＆ Kairi 大量ストック画像自動生成
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$ForgeDir = Join-Path $ScriptDir "sd-webui-forge"
$LoraModelDir = Join-Path $ForgeDir "models\Lora"
$OutputGalleryDir = Join-Path $ProjectRoot "img"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 🚀 Stable Diffusion WebUI Forge 構築＆大量画像自動生成スタジオ" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Forge のクローンと確認
if (-not (Test-Path $ForgeDir)) {
    Write-Host "`n[1/3] SD WebUI Forge を GitHub からダウンロードしています..." -ForegroundColor Yellow
    git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git $ForgeDir
} else {
    Write-Host "`n[1/3] SD WebUI Forge はすでに存在します: $ForgeDir" -ForegroundColor Green
}

# 2. 学習済み LoRA モデルの自動配置
Write-Host "`n[2/3] 学習済み LoRA の配置を確認中..." -ForegroundColor Yellow
if (-not (Test-Path $LoraModelDir)) {
    New-Item -ItemType Directory -Force -Path $LoraModelDir | Out-Null
}
$TrainedLora = Join-Path $ScriptDir "output\kairi_v1.safetensors"
if (Test-Path $TrainedLora) {
    Copy-Item $TrainedLora -Destination $LoraModelDir -Force
    Write-Host "  -> 学習済み kairi_v1.safetensors を Forge のモデルフォルダへ配置しました！" -ForegroundColor Green
} else {
    Write-Host "  -> 注意: まだ output\kairi_v1.safetensors が見つかりません。先に setup_kohya_and_train.ps1 で学習を行ってください。" -ForegroundColor Gray
}

# 3. 大量自動生成 Python バッチスクリプトの作成
$BatchGenScript = Join-Path $ScriptDir "run_batch_generator.py"
$BatchPython = @"
import urllib.request
import json
import base64
import os
import time

# WebUI Forge ローカル API URL
API_URL = "http://127.0.0.1:7860/sdapi/v1/txt2img"
OUTPUT_DIR = r"$OutputGalleryDir"

os.makedirs(OUTPUT_DIR, exist_ok=True)

prompts = [
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, energetic big smile, gyaru style, cute casual fashion, cafe background, masterpiece, best quality, ultra-detailed",
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, gentle smile, white hoodie, street background, masterpiece, best quality, ultra-detailed",
    "<lora:kairi_v1:1.0>, kairi, 1girl, anime style, long caramel brown twintails, amber eyes, winking, peace sign, selfie pose, bedroom background, masterpiece, best quality, ultra-detailed"
]

print("🎨 [Kairi Batch Studio] 大量ストック画像の自動生成を開始します...")
for idx, p in enumerate(prompts * 10):  # 30枚連続生成
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
                print(f"  -> ✅ 生成完了＆ストック追加: {filepath}")
    except Exception as e:
        print(f"  -> ❌ エラー: {e} (WebUI Forge が起動して --api オプションがついているか確認してください)")

print("🎉 すべての自動生成バッチが完了しました！")
"@
Set-Content -Path $BatchGenScript -Value $BatchPython -Encoding UTF8

Write-Host "`n[3/3] 大量生成スクリプト($BatchGenScript)を作成しました！" -ForegroundColor Green
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "📌 Forge の起動とストック大量作成の流れ:" -ForegroundColor White
Write-Host " 1. sd-webui-forge フォルダ内の webui-user.bat を右クリック編集し、COMMANDLINE_ARGS=--api と書いて保存・起動します。" -ForegroundColor Gray
Write-Host " 2. WebUI が立ち上がったら、別のコマンド画面で `python run_batch_generator.py` を実行するだけ！" -ForegroundColor Gray
Write-Host " 3. img/ フォルダに最高画質ストックがどんどんたまっていきます！" -ForegroundColor Gray
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
