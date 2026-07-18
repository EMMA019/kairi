@echo off
cd /d "%~dp0"
echo ==================================================================
echo [LoRA Studio] Launching SD WebUI Forge Setup and Batch Generator...
echo ==================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_webui_forge_and_batch_generate.ps1"
pause
