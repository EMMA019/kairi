#!/usr/bin/env python3
"""
Kairi Chat AI — デスクトップ買い切りエディション 一発起動ランチャー
単一ファイル(.exe)化やダブルクリック起動用のデスクトップエントリポイント
"""
import sys
import os
import time
import webbrowser
import threading
import uvicorn
from pathlib import Path

# バックエンドパスの追加
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

def run_server(port=8000):
    """FastAPI サーバーを実行"""
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False
    )

def main():
    port = 8000
    print(f"🛡️ Starting Kairi Desktop AI Engine on port {port}...")
    
    # バックグラウンドスレッドで FastAPI サーバーを起動
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    
    # サーバーの立ち上がりを待機してからアプリ画面を開く
    time.sleep(1.5)
    app_url = f"http://127.0.0.1:{port}/"
    print(f"🚀 Opening Kairi Desktop Application: {app_url}")
    webbrowser.open(app_url)

    try:
        # メインスレッドをキープ
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Kairi Desktop Engine...")
        sys.exit(0)

if __name__ == "__main__":
    main()
