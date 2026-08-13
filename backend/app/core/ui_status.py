"""Localized UI / pipeline status strings for SSE progress (settings.locale)."""
from __future__ import annotations

from app.core.reply_language import normalize_locale

_PIPELINE = {
    "intent_analysis": {
        "en": "Analyzing intent and whether search is needed...",
        "ja": "ユーザーの意図と検索要否を分析中...",
    },
    "fact_checking": {
        "en": "Cross-checking search results and context...",
        "ja": "検索結果とコンテキストを照合・検証中...",
    },
    "composing": {
        "en": "Composing the answer...",
        "ja": "回答を構成・生成中...",
    },
    "searching": {
        "en": "Gathering information: {q}",
        "ja": "情報収集中: {q}",
    },
    "re_run_tests": {
        "en": "Re-running with test results applied…",
        "ja": "テスト結果を反映して再実行中…",
    },
    "fix_and_retry": {
        "en": "Retrying after error fix…",
        "ja": "エラー修正のため再実行中…",
    },
    "empty_tool_retry": {
        "en": "Retrying because the tool returned empty…",
        "ja": "ツール結果が空だったため再試行中…",
    },
    "empty_regen": {
        "en": "Regenerating after an empty response…",
        "ja": "空応答だったため再生成中…",
    },
    "save_long_then_body": {
        "en": "Saving long text to a file, then putting it back into the answer…",
        "ja": "長文をファイル保存してから本文へ載せ直します…",
    },
    "compose_from_search": {
        "en": "Composing answer from search results…",
        "ja": "検索結果から回答を構成中…",
    },
    "system_error": {
        "en": "A system error occurred. Could not complete the request.",
        "ja": "システムエラーが発生しました。処理を完了できませんでした。",
    },
}


def pipeline_detail(key: str, locale: str | None = None, **kwargs: object) -> str:
    loc = normalize_locale(locale)
    entry = _PIPELINE.get(key) or {}
    template = entry.get(loc) or entry.get("en") or key
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def get_ui_locale() -> str:
    """Current settings.locale for user-facing filter footnotes."""
    try:
        from app.routers.settings import app_settings

        return normalize_locale(app_settings.get().get("locale", "en"))
    except Exception:
        return "en"


# ドメイン別の文言はコンテキスト判定を誤ると見当違いな注記になるため、
# 種類を問わず同一の一般的注意喚起に一本化する。
_DISCLAIMERS = {
    "ai_caution": {
        "en": (
            "\n\nNote: AI can make mistakes. "
            "Please double-check important figures, dates, and prices with official sources."
        ),
        "ja": (
            "\n\n※ AIは間違えることがあります。"
            "重要な数値・日程・価格は公式情報でご確認ください。"
        ),
    },
}

# 既存本文に注記が入っているかの判定用（旧ドメイン別文言も二重付与しない）
_AI_CAUTION_MARKERS = (
    "AIは間違えることがあります",
    "AI can make mistakes",
    # レガシー文言（過去ログ・履歴の再処理で二重に付かないよう残す）
    "※一部の比率",
    "公式開示",
    "Some ratios, market indicators",
    "official disclosures",
    "※お出かけ前に",
    "Please confirm with official",
    "Please check the latest",
)


def disclaimer(key: str, locale: str | None = None, **kwargs: object) -> str:
    loc = normalize_locale(locale) if locale is not None else get_ui_locale()
    entry = _DISCLAIMERS.get(key) or {}
    template = entry.get(loc) or entry.get("en") or ""
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template


def has_ai_caution(text: str) -> bool:
    """一般注意喚起（または旧ドメイン別注記）が既に入っているか。"""
    if not text:
        return False
    return any(m in text for m in _AI_CAUTION_MARKERS)
