#!/usr/bin/env python3
"""
Kairi Desktop launcher — binds 127.0.0.1 only; KAIRI_RELEASE=1 hides OpenAPI.
"""
import sys
import os
import time
import webbrowser
import threading
from pathlib import Path

os.environ.setdefault("KAIRI_RELEASE", "1")
os.environ.setdefault("ALLOW_OPEN_CORS", "0")
# Radar / briefing schedulers stay off in release unless explicitly enabled
os.environ.setdefault("KAIRI_ENABLE_SCHEDULERS", "0")

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def run_server(port=8000):
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False,
    )


def main():
    port = int(os.environ.get("KAIRI_PORT", "8000"))
    print(f"Starting Kairi Desktop on http://127.0.0.1:{port}/ ...")
    print("(First run: paste DeepSeek API key in the browser wizard. Data stays on this PC.)")

    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    time.sleep(2.0)
    app_url = f"http://127.0.0.1:{port}/"
    print(f"Opening {app_url}")
    webbrowser.open(app_url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down Kairi Desktop...")
        sys.exit(0)


if __name__ == "__main__":
    main()
