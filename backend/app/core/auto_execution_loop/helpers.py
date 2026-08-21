"""Shared helpers for the auto-execution loop (UI progress, visibility snapshots)."""
from __future__ import annotations

import re

from app.utils.logger import get_logger

logger = get_logger(__name__)


def error_signature(error_info: str) -> str:
    """エラー文本を重複検出用の正規化シグネチャに変換する。"""
    return re.sub(r"\s+", " ", str(error_info or "")).strip()[:150]


# Back-compat alias used by tests / older imports
_error_signature = error_signature


def snapshot_visible(text: str) -> str:
    """ユーザーに見せられる本文だけを抽出して保持用に返す。"""
    try:
        from app.core.fact_filters.markup import clean_assistant_visible

        return clean_assistant_visible(text or "")
    except Exception:
        return re.sub(r"<[^>]+>", "", text or "").strip()


_snapshot_visible = snapshot_visible


def remember_good(current: str, candidate: str) -> str:
    try:
        from app.core.fact_filters.markup import normalize_final_answer_body

        body, empty_after = normalize_final_answer_body(candidate or "")
        if empty_after:
            return current
        vis = snapshot_visible(body)
    except Exception:
        vis = snapshot_visible(candidate)
    if vis and len(vis) >= 8:
        return vis
    return current


_remember_good = remember_good


def ui_progress(key: str, **kwargs) -> str:
    from app.routers.settings import app_settings
    from app.core.ui_status import pipeline_detail

    return pipeline_detail(key, app_settings.get().get("locale", "en"), **kwargs)


_ui_progress = ui_progress


def clear_ui_with_progress(yield_sse_func, detail: str) -> None:
    """
    clear_buffer で画面を空にしない。進捗を pipeline + chunk で残し、
    「裏で動いてるのに応答空」の体感と無駄リトライを減らす。
    """
    if not yield_sse_func:
        return
    yield_sse_func({"type": "clear_buffer"})
    yield_sse_func({"type": "pipeline", "stage": "working", "detail": detail})
    yield_sse_func({"type": "status", "status": "responding"})
    yield_sse_func({"type": "chunk", "content": f"⏳ {detail}\n"})


_clear_ui_with_progress = clear_ui_with_progress


BOUNDARY_INSTRUCTION = (
    "\n\n【構造的モダリティ分離（出力境界トークン）の厳守ルール】\n"
    "思考ログ・内部分析・途中メモとユーザーへの最終出力本文がバッファ上で混在するのを完全に防ぐため、"
    "ユーザーへの最終的な回答本文を開始する直前に必ず `<<<FINAL_ANSWER>>>` という区切りトークンを出力し、"
    "その後にのみ最終回答テキストを出力してください。\n"
    "※ツール呼び出し（<search>, <file> 等）のみを行うターンでは `<<<FINAL_ANSWER>>>` は不要です。"
)

UNIVERSAL_CLOSED_WORLD_INSTRUCTION = (
    "\n\n【全ドメイン適用：動的・時系列クエリにおける完全閉世界（Closed-World）原則とパラメトリック記憶の遮断】\n"
    "現在は2026年です。政治、経済・金融（FRB/中央銀行/指標等）、企業人事（CEO/役員等）、スポーツ（選手/所属/監督）、"
    "エンタメ、テクノロジー等の時系列動向・最新ファクトに関する質問に対しては、事前学習データ（パラメトリック記憶）にある"
    "過去の固有名詞や人名（例：FRBパウエル議長等）を絶対にそのまま出力せず、必ず直近の検索結果（ソーステキスト）に明示的に"
    "記載されている最新の人名・固有エンティティのみを正確に拾って回答すること。\n"
    "ソーステキストに個人名の記載がなく役職名・肩書のみ（『FRB議長』『同社CEO』『現職監督』等）記載されている場合は、"
    "勝手に過去の記憶から個人名を推測・補完・上書きせず、ソース通りに『FRB議長』『同社CEO』のように役職名・一般名詞のみで記述してください。"
)

NO_SOURCE_GUARD = (
    "\n\n【🔴 ソースなしターン：固有名詞断定の厳禁】\n"
    "このターンは検索ソースがありません。"
    "会話履歴・ユーザー発言に明示されていない時事的固有名詞"
    "（人名・騎手・役職・所属・記録値・オッズ・日付付きイベント結果）を新規に断定することを禁止します。"
    "必要なら『〜だったはず（要確認）』の不確実表現にするか、"
    "先に <search query=\"...\" /> タグで検索を実行してください。"
    "パラメトリック記憶（事前学習データ）からの補完は絶対に行わないこと。"
)


def ensure_executor_guards(executor_sys_prompt: str, *, has_search: bool) -> str:
    """Append closed-world / FINAL_ANSWER / no-source guards once."""
    prompt = executor_sys_prompt or ""
    if "完全閉世界（Closed-World）原則" not in prompt:
        prompt += UNIVERSAL_CLOSED_WORLD_INSTRUCTION
    if not has_search and "ソースなしターン" not in prompt:
        prompt += NO_SOURCE_GUARD
    if has_search and "引用ファースト" not in prompt:
        prompt += (
            "\n\n【引用ファースト】検索結果があるターンでは、"
            "ソース [n] の抜粋に無い固有名・数値を本文に足すな。"
            "断定する文には [n] を付け、足りない事実は省略せよ。"
        )
    if "<<<FINAL_ANSWER>>>" not in prompt:
        prompt += BOUNDARY_INSTRUCTION
    return prompt
