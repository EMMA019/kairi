@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================================
echo 🎭 Kairi LoRA ワンクリック学習環境を起動しています...
echo ==================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_kohya_and_train.ps1"
pause
