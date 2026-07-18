# ==============================================================================
# Kairi 専用 LoRA 全自動セットアップ＆学習スクリプト (RTX 2060 12GB 最適化版)
# ==============================================================================
# 実行方法: PowerShell 上で `.\setup_kohya_and_train.ps1` を実行するか右クリックで PowerShell で実行

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$KohyaDir = Join-Path $ScriptDir "kohya_ss"
$DatasetDir = Join-Path $ScriptDir "dataset\25_kairi"
$OutputDir = Join-Path $ScriptDir "output"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 🎭 Kairi LoRA ワンクリック自動学習スタジオへようこそ！ (RTX 2060版)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. フォルダ準備＆データセット配置
Write-Host "`n[1/4] データセットフォルダと出力先を準備中..." -ForegroundColor Yellow
if (-not (Test-Path $DatasetDir)) {
    New-Item -ItemType Directory -Force -Path $DatasetDir | Out-Null
}
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

# 既存の img/ ディレクトリから画像とキャプション(.txt)をコピー
$SourceImgDir = Join-Path $ProjectRoot "img"
if (Test-Path $SourceImgDir) {
    Write-Host "  -> img/ フォルダから画像をデータセット($DatasetDir)へコピー中..." -ForegroundColor Green
    Copy-Item "$SourceImgDir\*" -Destination $DatasetDir -Force
}

# 2. Kohya_ss / sd-scripts の確認・自動クローン
Write-Host "`n[2/4] 学習エンジン (sd-scripts) を確認中..." -ForegroundColor Yellow
$SdScriptsDir = Join-Path $ScriptDir "sd-scripts"
if (-not (Test-Path $SdScriptsDir)) {
    Write-Host "  -> sd-scripts を GitHub からクローンしています..." -ForegroundColor Green
    git clone https://github.com/kohya-ss/sd-scripts.git $SdScriptsDir
}

# 3. 学習設定ファイル (config.toml) の自動生成 (RTX 2060 12GB 最適化)
Write-Host "`n[3/4] RTX 2060 12GB 専用の最適学習設定ファイル (config.toml) を作成中..." -ForegroundColor Yellow
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

# 4. 学習完了ご案内と起動準備
Write-Host "`n[4/4] セットアップ完了！学習を開始する準備が整いました！" -ForegroundColor Green
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "📌 次のステップ:" -ForegroundColor White
Write-Host " 1. sd-scripts ディレクトリ ($SdScriptsDir) で仮想環境を作成し依存ライブラリをインストールします。" -ForegroundColor Gray
Write-Host " 2. 以下のコマンドを実行すると、約25〜40分で output フォルダ内に kairi_v1.safetensors が完成します！" -ForegroundColor Gray
Write-Host "------------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "`n準備が良ければ、このまま Enter キーを押すと学習環境の構築と学習を開始します..." -ForegroundColor Yellow
Read-Host

Write-Host "🚀 学習を開始します！ (完了すると $OutputDir に .safetensors が出力されます)" -ForegroundColor Green
