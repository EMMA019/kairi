# ==============================================================================
# Kairi LoRA Auto Setup and Train Script (RTX 2060 12GB Optimized)
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$KohyaDir = Join-Path $ScriptDir "kohya_ss"
$DatasetDir = Join-Path $ScriptDir "dataset\25_kairi"
$OutputDir = Join-Path $ScriptDir "output"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Kairi LoRA Auto Setup and Training Studio (RTX 2060 12GB)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

Write-Host "`n[1/4] Preparing dataset directory and output directory..." -ForegroundColor Yellow
if (-not (Test-Path $DatasetDir)) { New-Item -ItemType Directory -Force -Path $DatasetDir | Out-Null }
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null }

$SourceImgDir = Join-Path $ProjectRoot "img"
if (Test-Path $SourceImgDir) {
    Write-Host "  -> Copying images and captions from img/ to dataset ($DatasetDir)..." -ForegroundColor Green
    Copy-Item "$SourceImgDir\*" -Destination $DatasetDir -Force
}

Write-Host "`n[2/4] Checking training engine (sd-scripts)..." -ForegroundColor Yellow
$SdScriptsDir = Join-Path $ScriptDir "sd-scripts"
if (-not (Test-Path $SdScriptsDir)) {
    Write-Host "  -> Cloning sd-scripts from GitHub..." -ForegroundColor Green
    git clone https://github.com/kohya-ss/sd-scripts.git $SdScriptsDir
}

Write-Host "`n[3/4] Creating optimized dataset_config.toml for RTX 2060..." -ForegroundColor Yellow
$ConfigFile = Join-Path $ScriptDir "dataset_config.toml"
$ConfigContent = @"
[general]
enable_bucket = true

[[datasets]]
resolution = 512
batch_size = 1

  [[datasets.subsets]]
  image_dir = "$DatasetDir"
  class_tokens = "kairi 1girl"
  num_repeats = 15
"@
Set-Content -Path $ConfigFile -Value $ConfigContent -Encoding UTF8

Write-Host "`n[4/4] Setup complete! Ready to start training." -ForegroundColor Green
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor White
Write-Host " 1. Create virtualenv in $SdScriptsDir and install dependencies." -ForegroundColor Gray
Write-Host " 2. Run the train command to build kairi_v1.safetensors in about 30 mins!" -ForegroundColor Gray
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "`nPress Enter to begin or Ctrl+C to exit..." -ForegroundColor Yellow
Read-Host
Write-Host "Starting training process..." -ForegroundColor Green
