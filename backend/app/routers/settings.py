"""
設定管理ルーター。
LLMプロバイダー/モデル名の動的切り替えをサポート。
kv_store.py と同じシングルトン + JSON永続化パターン。
"""
import json
import os
import tempfile
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

SETTINGS_PATH = Path(__file__).parent.parent.parent / "storage" / "settings.json"

# Anthropic モデル固定リスト
ANTHROPIC_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

# Gemini モデル固定リスト
GEMINI_MODELS = [
    "gemini-3.1-pro",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]

# DeepSeek モデル固定リスト
DEEPSEEK_MODELS = [
    "deepseek-v4-pro",
    "deepseek-v4-flash",
]

# OpenAI モデル固定リスト
OPENAI_MODELS = [
    "gpt-5.5-pro",
    "gpt-5.5",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
]

_DEFAULT_SETTINGS = {
    "supervisor_provider": "deepseek",
    "supervisor_model": "deepseek-v4-pro",
    "executor_provider": "gemini",
    "executor_model": "gemini-3.1-pro",
    "planner_provider": "deepseek",
    "planner_model": "deepseek-v4-flash",
    "user_name": "ご主人様",
    "persona_style": "standard",
    "locale": "ja",
    "gemini_api_key": "",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "deepseek_api_key": "",
    "brave_api_key": "",
    "world_news_api_key": "",
    "newsdata_api_key": "",
    "is_licensed": True,
    "license_key": "KAIRI-PRO-ESTABLISHED",
    "app_pin": "",
}


class Settings:
    """設定のシングルトン管理（kv_store.py と同パターン）"""

    def __init__(self):
        self._settings: dict = {}
        self._last_mtime = 0
        self._load()

    def _sync_env(self):
        """ローカル保存されたAPIキーを os.environ に自動反映し、検索やLLM実行器がシームレスに利用可能にする"""
        env_map = {
            "gemini_api_key": "GEMINI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
            "deepseek_api_key": "DEEPSEEK_API_KEY",
            "brave_api_key": "BRAVE_API_KEY",
            "world_news_api_key": "WORLD_NEWS_API_KEY",
            "newsdata_api_key": "NEWSDATA_API_KEY",
        }
        for k, env_key in env_map.items():
            val = self._settings.get(k)
            if val:
                os.environ[env_key] = str(val)

    def _load(self):
        if SETTINGS_PATH.exists():
            try:
                self._last_mtime = SETTINGS_PATH.stat().st_mtime
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._settings = {**_DEFAULT_SETTINGS, **loaded}
                logger.info(f"設定をロード: {self._settings}")
            except Exception as e:
                logger.info(f"設定ロード失敗、デフォルトを使用: {e}")
                self._settings = _DEFAULT_SETTINGS.copy()
                self._save()
        else:
            self._settings = _DEFAULT_SETTINGS.copy()
            self._save()
        self._sync_env()

    def _save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(SETTINGS_PATH.parent), suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(SETTINGS_PATH))
        except Exception as e:
            logger.error(f"設定保存エラー: {e}")
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def get(self) -> dict:
        if SETTINGS_PATH.exists():
            try:
                mtime = SETTINGS_PATH.stat().st_mtime
                if mtime > getattr(self, "_last_mtime", 0):
                    self._last_mtime = mtime
                    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        self._settings = {**_DEFAULT_SETTINGS, **loaded}
                    self._sync_env()
            except Exception:
                pass
        return self._settings.copy()

    def update(self, update_data: dict):
        for k, v in update_data.items():
            if v is not None:
                self._settings[k] = v
        self._save()
        self._sync_env()
        logger.info(f"設定更新: {self._settings}")


# シングルトンインスタンス
app_settings = Settings()


class SettingsUpdate(BaseModel):
    supervisor_provider: Optional[str] = None
    supervisor_model: Optional[str] = None
    executor_provider: Optional[str] = None
    executor_model: Optional[str] = None
    planner_provider: Optional[str] = None
    user_name: Optional[str] = None
    persona_style: Optional[str] = None
    locale: Optional[str] = None
    gemini_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    brave_api_key: Optional[str] = None
    world_news_api_key: Optional[str] = None
    newsdata_api_key: Optional[str] = None
    is_licensed: Optional[bool] = None
    license_key: Optional[str] = None
    app_pin: Optional[str] = None


@router.get("/settings")
async def get_settings():
    """現在の設定を取得"""
    settings = app_settings.get()
    return {
        **settings,
        "available_providers": ["anthropic", "openai", "gemini", "deepseek", "local"],
        "anthropic_models": ANTHROPIC_MODELS,
        "gemini_models": GEMINI_MODELS,
        "deepseek_models": DEEPSEEK_MODELS,
        "openai_models": OPENAI_MODELS,
    }


@router.post("/settings")
async def update_settings(req: SettingsUpdate):
    """設定を更新"""
    app_settings.update(req.model_dump(exclude_unset=True))
    return {
        "status": "ok",
        **app_settings.get(),
    }
