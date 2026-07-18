@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================================
echo 🚀 SD WebUI Forge 構築＆ストック大量自動生成環境を起動しています...
echo ==================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_webui_forge_and_batch_generate.ps1"
pause
