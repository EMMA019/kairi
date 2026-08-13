"""プロセス内セッション状態と一時 settings の共通置き場。

ディスク永続化シングルトン (app_settings) と、プロセス辞書に散らばった
セッション状態をこれ以上増やさないための入口。
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


# --- search carryover（chat_search から移設する本体） ---
_MAX_SEARCH_CARRY_SESSIONS = 200
_last_search_by_session: dict[str, dict] = {}


def get_search_carryover_store() -> dict[str, dict]:
    return _last_search_by_session


def get_max_search_carry_sessions() -> int:
    return _MAX_SEARCH_CARRY_SESSIONS


@contextmanager
def temporary_settings(**overrides: Any) -> Iterator[None]:
    """app_settings を一時変更し、必ず元に戻す。

    テストや eval がディスク上の locale 等を汚さないための共通手段。
    """
    from app.routers.settings import app_settings

    original = {k: app_settings.get().get(k) for k in overrides}
    try:
        if overrides:
            app_settings.update(overrides)
        yield
    finally:
        # None は update が無視するため、欠落キーはデフォルトへ戻す
        restore = {}
        for k, v in original.items():
            if v is None and k == "locale":
                restore[k] = "en"
            elif v is not None:
                restore[k] = v
        if restore:
            app_settings.update(restore)
