"""
Supervisor → おまかせゲート → plan/hearing → Executor 連携のヘルパー。
メイン SSE ループは routers/chat.py が保持し、判断ロジックをここに寄せる。
"""
from __future__ import annotations

from typing import Any, Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


def build_executor_instruction(supervisor_json: dict, *, search_unsupported: bool = False) -> str:
    """Supervisor JSON から Executor 向け instruction 文字列を組み立てる。"""
    instruction_dict = supervisor_json.get("instruction", {})
    if isinstance(instruction_dict, dict):
        facts = instruction_dict.get("facts_to_present", [])
        order = instruction_dict.get("logical_order", [])
        instruction = ""
        if facts:
            instruction += "【必ず含めるべき事実】\n"
            for f in facts:
                instruction += f"- {f}\n"
        if order:
            instruction += "\n【回答の構成（順序）】\n"
            for o in order:
                instruction += f"- {o}\n"
    else:
        instruction = str(instruction_dict)

    if search_unsupported:
        from app.core.search_relevance import SEARCH_UNSUPPORTED_INSTRUCTION
        instruction = (SEARCH_UNSUPPORTED_INSTRUCTION + "\n\n" + (instruction or "")).strip()
    return instruction


def apply_omakase_hearing_ban(user_input: str, mode: str, supervisor_json: dict) -> tuple[str, dict]:
    """おまかせ開発依頼で hearing へ逃避した場合に chat+plan へ強制転換。"""
    from app.core.omakase_policy import is_omakase_dev_request

    if not (is_omakase_dev_request(user_input) and mode == "hearing"):
        return mode, supervisor_json

    logger.warning("おまかせ開発依頼なのに mode=hearing → chat+plan に強制転換")
    mode = "chat"
    supervisor_json["mode"] = "chat"
    supervisor_json["hearing_state"] = None
    if not supervisor_json.get("plan"):
        inst = supervisor_json.get("instruction") or {}
        if isinstance(inst, dict):
            facts = inst.get("logical_order") or []
            if isinstance(facts, list):
                facts = [
                    "おまかせ開発依頼のためヒアリングせず、最良案を1つ決断して具体プランを提示すよ",
                    "予算内訳・成果物・7日手順・人間必須作業・成功指標を必ず含めること",
                    "コーディング可否・趣味・作業時間は質問しない。確認は方針のYes/Noのみ",
                ] + list(facts)
                inst["logical_order"] = facts
            supervisor_json["instruction"] = inst
    return mode, supervisor_json


def resolve_memory_inject(
    supervisor_json: dict,
    filtered_kv_text: str,
) -> tuple[dict, Optional[str]]:
    """memory_inject をスコープ付き KV に合わせて正規化し、注入テキストを返す。"""
    if not filtered_kv_text:
        if supervisor_json.get("memory_inject"):
            logger.warning("memory_inject=true を拒否（スコープ内の記憶なし）")
        supervisor_json["memory_inject"] = False
    memory_to_inject = (
        filtered_kv_text if supervisor_json.get("memory_inject") and filtered_kv_text else None
    )
    return supervisor_json, memory_to_inject


def note_search_inject(search_results_text: Optional[str], supervisor_json: dict) -> Optional[str]:
    """検索結果があれば常に注入（search_used 自己申告を信用しない）。"""
    if search_results_text and not supervisor_json.get("search_used"):
        logger.info("📎 search_used=false だが検索結果が存在するため Executor へ注入します")
    return search_results_text
