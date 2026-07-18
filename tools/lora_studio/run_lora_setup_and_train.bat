@echo off
cd /d "%~dp0"
echo ==================================================================
echo [LoRA Studio] Launching Kairi LoRA One-Click Setup and Training...
echo ==================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_kohya_and_train.ps1"
pause
