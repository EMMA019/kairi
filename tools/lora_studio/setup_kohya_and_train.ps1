# ==============================================================================
# Kairi LoRA Auto Setup and Train Script (RTX 2060 12GB Optimized)
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$KohyaDir = Join-Path $ScriptDir "kohya_ss"
$DatasetDir = Join-Path $ScriptDir "dataset\25_kairi"
$OutputDir = Join-Path $ScriptDir "output"
$BaseModelDir = Join-Path $ScriptDir "base_models"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Kairi LoRA Auto Setup and Training Studio (RTX 2060 12GB)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host "`n[1/5] Preparing dataset and output directories..." -ForegroundColor Yellow
if (-not (Test-Path $DatasetDir)) { New-Item -ItemType Directory -Force -Path $DatasetDir | Out-Null }
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null }
if (-not (Test-Path $BaseModelDir)) { New-Item -ItemType Directory -Force -Path $BaseModelDir | Out-Null }

$SourceImgDir = Join-Path $ProjectRoot "img"
if (Test-Path $SourceImgDir) {
    Write-Host "  -> Syncing high-precision WD14 images and tags to dataset directory..." -ForegroundColor Green
    Copy-Item "$SourceImgDir\*" -Destination $DatasetDir -Force
}

Write-Host "`n[2/5] Checking training engine (sd-scripts)..." -ForegroundColor Yellow
$SdScriptsDir = Join-Path $ScriptDir "sd-scripts"
if (-not (Test-Path $SdScriptsDir)) {
    Write-Host "  -> Cloning sd-scripts from GitHub..." -ForegroundColor Green
    git clone https://github.com/kohya-ss/sd-scripts.git $SdScriptsDir
}

Write-Host "`n[3/5] Creating optimized dataset_config.toml for RTX 2060..." -ForegroundColor Yellow
$ConfigFile = Join-Path $ScriptDir "dataset_config.toml"
$DatasetDirClean = $DatasetDir.Replace('\', '/')
$ConfigContent = @"
[general]
enable_bucket = true

[[datasets]]
resolution = 1024
batch_size = 1

  [[datasets.subsets]]
  image_dir = "$DatasetDirClean"
  class_tokens = "kairi 1girl"
  num_repeats = 15
"@
[System.IO.File]::WriteAllText($ConfigFile, $ConfigContent, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "`n[4/5] Checking Python Virtual Environment & PyTorch CUDA setup..." -ForegroundColor Yellow
$VenvDir = Join-Path $SdScriptsDir "venv"
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvDir)) {
    Write-Host "  -> Creating Python virtual environment inside sd-scripts..." -ForegroundColor Green
    python -m venv $VenvDir
    Write-Host "  -> Upgrading pip and installing PyTorch 2.4.0 (CUDA 12.1 golden set)..." -ForegroundColor Green
    & $PipExe install --upgrade pip
    & $PipExe install torch==2.4.0+cu121 torchvision==0.19.0+cu121 xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu121
    Write-Host "  -> Installing sd-scripts requirements and compatible OpenCV/NumPy..." -ForegroundColor Green
    Push-Location $SdScriptsDir
    & $PipExe install -r requirements.txt diffusers transformers accelerate tqdm toml albumentations tensorboard safetensors huggingface_hub scipy bitsandbytes "numpy<2" "opencv-python-headless<5" "opencv-python<5"
    Pop-Location
    & $PipExe install lion-pytorch prodigyopt
} else {
    Write-Host "  -> Virtual environment already installed and ready at: $VenvDir" -ForegroundColor Green
}

Write-Host "`n[5/5] Setup complete! Preparing training parameters..." -ForegroundColor Green
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Training Configuration Summary:" -ForegroundColor White
Write-Host " - Target: Kairi Character LoRA (kairi_v1.safetensors)" -ForegroundColor Gray
Write-Host " - Dataset: 25 high-precision WD14 tagged images (15 repeats x 25 = 375 steps/epoch)" -ForegroundColor Gray
Write-Host " - GPU: RTX 2060 (12GB VRAM optimized: fp16, 8-bit AdamW, memory efficient attention)" -ForegroundColor Gray
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "`nPress Enter to begin automated LoRA training right now (or Ctrl+C to exit)..." -ForegroundColor Yellow
Read-Host

Write-Host "`n🚀 Launching training process right now..." -ForegroundColor Green
$TrainScript = Join-Path $SdScriptsDir "sdxl_train_network.py"

# Base model: Animagine XL or any SDXL model. We will ask user to copy it to base_models or we point to the Forge one.
$BaseModel = Join-Path $ScriptDir "sd-webui-forge\models\Stable-diffusion\animagineXL40_v4Opt.safetensors"
if (-not (Test-Path $BaseModel)) {
    # Fallback to local base_models dir
    $BaseModel = Join-Path $BaseModelDir "animagineXL40_v4Opt.safetensors"
}
if (-not (Test-Path $BaseModel)) {
    Write-Host "Warning: Base model animagineXL40_v4Opt.safetensors not found in standard paths. Training might fail!" -ForegroundColor Red
}

& $PythonExe $TrainScript `
    --pretrained_model_name_or_path="$BaseModel" `
    --dataset_config="$ConfigFile" `
    --output_dir="$OutputDir" `
    --output_name="kairi_v1" `
    --save_model_as=safetensors `
    --prior_loss_weight=1.0 `
    --max_train_epochs=10 `
    --learning_rate=1e-4 `
    --optimizer_type="AdamW8bit" `
    --xformers `
    --mixed_precision="fp16" `
    --save_precision="fp16" `
    --network_module=networks.lora `
    --network_dim=32 `
    --network_alpha=16 `
    --network_train_unet_only `
    --cache_latents `
    --cache_text_encoder_outputs `
    --gradient_checkpointing

Write-Host "`n🎉 Training Finished! Your custom SDXL Kairi LoRA is saved at: $OutputDir\kairi_v1.safetensors" -ForegroundColor Green
