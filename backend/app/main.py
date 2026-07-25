"""
Kairi Chat AI — FastAPI エントリーポイント
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込み（他のモジュールで環境変数を使うため、最初に行う）
load_dotenv()
_main_logger = logging.getLogger("app.main")

from app.core.database import init_db
from app.core.news.database import init_db as init_news_db
from app.core.news.scheduler import setup_scheduler, shutdown_scheduler
from app.core.cache_manager import init_cache_db
from app.core.monitor.scheduler import start_radar_scheduler, stop_radar_scheduler
from app.routers import chat, history, memory, logs, mood, upload, settings, workspace, project, tools, image, integrity


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    # 起動時: DB 初期化
    await init_db()
    await init_news_db()
    await init_cache_db()
    setup_scheduler()  # スタブ（定期RSSは廃止）
    start_radar_scheduler()  # 24時間無人市場監視レーダー自動巡回開始
    yield
    # 終了時: クリーンアップ
    stop_radar_scheduler()
    shutdown_scheduler()
    from app.core.search.providers.http_client import close_http_client
    await close_http_client()


app = FastAPI(
    title="Kairi Chat AI",
    description="自律型AIエージェント with Chat & IDE v2.1",
    version="2.1.1",
    lifespan=lifespan,
)

# CORS 設定（既定はローカル開発オリジンのみ。広域許可は ALLOW_OPEN_CORS=1 のときのみ）
_default_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://localhost",
    "https://localhost",
    "capacitor://localhost",
]
try:
    from app.routers.settings import app_settings as _cors_settings
    _configured = _cors_settings.get().get("allowed_origins") or []
    if isinstance(_configured, list) and _configured:
        _default_origins = list(dict.fromkeys(_default_origins + [str(o) for o in _configured]))
except Exception:
    pass

_cors_kwargs = {
    "allow_origins": _default_origins,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if os.environ.get("ALLOW_OPEN_CORS", "").strip() in ("1", "true", "TRUE", "yes"):
    # 明示オプトイン時のみ広域 regex を許可（Tailscale 等）
    _cors_kwargs["allow_origin_regex"] = r"(https?|capacitor)://.*"
    _main_logger.warning("⚠️ ALLOW_OPEN_CORS=1: 任意オリジンからの CORS を許可しています")
else:
    _main_logger.info("CORS: 許可オリジンをローカル開発リストに制限しています（広域は ALLOW_OPEN_CORS=1）")

app.add_middleware(CORSMiddleware, **_cors_kwargs)

# API トークン認証（api_token / KAIRI_API_TOKEN 未設定時は開発モードでスキップ）
from app.core.auth import APITokenMiddleware
app.add_middleware(APITokenMiddleware)

# ルーター登録
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(memory.router, prefix="/api", tags=["memory"])
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(mood.router, prefix="/api", tags=["mood"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(workspace.router, prefix="/api", tags=["workspace"])
app.include_router(project.router, prefix="/api", tags=["project"])
app.include_router(tools.router, prefix="/api", tags=["tools"])
app.include_router(image.router, prefix="/api", tags=["image"])
app.include_router(integrity.router, prefix="/api", tags=["integrity"])


@app.get("/api/ping")
@app.get("/ping")
async def ping():
    """Renderスリープ防止および死活監視用の軽量ヘルスチェックエンドポイント"""
    return {"status": "ok", "service": "kairi-chat-backend", "alive": True}


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# フロントエンド静的ビルドフォルダの検出とマウント (買い切りデスクトップアプリ対応)
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return {
            "app": "Kairi Chat AI",
            "version": "2.1.0",
            "status": "running",
            "message": "Frontend build not found. Run `npm run build` in frontend directory.",
        }
