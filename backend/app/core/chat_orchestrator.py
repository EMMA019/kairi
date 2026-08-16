"""
Supervisor → おまかせゲート → plan/hearing → Executor 連携のヘルパー。
メイン SSE ループは routers/chat.py が保持し、判断ロジックをここに寄せる。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 未完了再開（incomplete バナーの推奨発話）。プラン承認と絶対に混同しない
_CONTINUATION_PATTERNS = (
    r"続きを作成して",
    r"続きを作って",
    r"続きから",
    r"続けて(?:ください|下さい|くれ|実装|作成)?",
    r"^続き$",
    r"未完了から",
    r"再開して",
)

# 仕様書提示後の短い承認語（再 spec 禁止ゲート用）— 全文一致寄り
_SPEC_APPROVAL_PATTERNS = (
    r"^(はい|ええ|うん|OK|ok|Okay|okay|yes|Yes|YES|GO|go|◎|〇|○)[.!！。]?$",
    r"^(進めて|お願い|よろしく|それで|その方針で|その感じで|そんな感じで|作って|実装して|開始して|承認|いいよ|いいです|大丈夫|やろう|頼む)[.!！。]?$",
    r"^(とりま|そんな感じ|その感じ).{0,24}$",
)

# 実装プラン承認（pending_plan）— 部分一致禁止。「作成」が「続きを作成して」に誤ヒットしない
_PLAN_APPROVAL_PATTERNS = (
    r"^(はい|ええ|うん|OK|ok|Okay|okay|yes|Yes|YES|GO|go)[.!！。]?$",
    r"^(進めて|お願い|よろしくお願いします|よろしく|それで|その方針で|いいよ|いいです|大丈夫|やろう|頼む|承認|お願いします)[.!！。]?$",
    r"^(実装して|実装お願い|開始して|作って|作成して|作ってください|作成してください)[.!！。]?$",
)

# ユーザー向け本文に出さない委譲・内部指示
_FACT_SKIP_RE = re.compile(
    r"(<read_url|<read_file|<run_command|<file |<replace |<search|"
    r"回答を生成する前に|必ず .+ を出力|実行モデル)",
    re.IGNORECASE,
)

# hearing/spec に混ざる監督思考（モード議論・JSON設計）
# JSON形式 は仕様書の一括投入方式でも使うので入れない
_HEARING_META_RE = re.compile(
    r"mode\s*=\s*hearing|search_used|facts_to_present|hearing_state|"
    r"kv_action|violation_risk|"
    r"実行モデル|思考・監督|JSONで出力|"
    r"ユーザーは「.{0,80}」と言っている|"
    r"これは開発依頼|ヒアリング項目|ヒアリング中|"
    r"私は思考|監督モデル",
    re.IGNORECASE,
)
_SEARCH_QUERY_RE = re.compile(
    r"""<search\b[^>]*\bquery=["']([^"']+)["']""",
    re.IGNORECASE,
)
_HEARING_QUESTION_FALLBACK = "対象や作りたい形を、もう少し具体的に教えてください。"

_MEMORY_SAVE_SUCCESS_RE = re.compile(
    r"追加した|記憶した|保存した|覚えました|記憶済み|追加いたしました|追記した|追記いたしました|"
    r"added to memory|I (?:saved|remembered) (?:that|this|it)|saved (?:that|this) to memory",
    re.IGNORECASE,
)


_HEARING_SPEC_EXEC_RULES = (
    "【hearing/spec 本文ルール】ユーザー向け本文だけ書け。"
    "思考・JSON・mode 議論・facts_to_present は出すな。"
    "<file> <replace> <edit> <run_command> は禁止。足りない事実だけ <search> してよい。"
    "未検証・二次ソースの料金・級数・問題数は断定するな。検索に無い数字は「公式未確認」にする。"
)


def hearing_spec_tool_loop_cap(mode: str) -> int:
    """hearing/spec は検索だけの短いループ。実装ループにはしない。"""
    if mode in ("hearing", "spec_generation"):
        return 4
    return 40


def build_executor_instruction(
    supervisor_json: dict,
    *,
    search_unsupported: bool = False,
    mode: str = "",
) -> str:
    """Supervisor JSON から Executor 向け instruction 文字列を組み立てる。"""
    instruction_dict = supervisor_json.get("instruction", {})
    rejected = (supervisor_json.get("kv_action") or {}).get("rejected_reason")
    if isinstance(instruction_dict, dict):
        facts = list(instruction_dict.get("facts_to_present") or [])
        if rejected:
            facts = [f for f in facts if not _MEMORY_SAVE_SUCCESS_RE.search(str(f))]
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

    if rejected:
        note = (
            f"【記憶保存の結果】今回の内容はメモリに保存されませんでした（{rejected}）。"
            "「メモリに追加しました」「記憶しました」「I saved that」「added to memory」等の成功表現は禁止。"
            "保存できなかった旨を短く伝え、必要なら「覚えておいて」「メモリに追加」"
            "/ remember this / add to memory など明示的な保存の言い方を案内すること。"
        )
        instruction = (note + "\n\n" + (instruction or "")).strip()

    if search_unsupported:
        from app.core.search_relevance import SEARCH_UNSUPPORTED_INSTRUCTION
        instruction = (SEARCH_UNSUPPORTED_INSTRUCTION + "\n\n" + (instruction or "")).strip()

    if mode in ("hearing", "spec_generation"):
        draft = (
            compose_hearing_user_text(supervisor_json)
            if mode == "hearing"
            else compose_spec_user_text(supervisor_json)
        )
        instruction = (
            f"{_HEARING_SPEC_EXEC_RULES}\n\n"
            f"【下書き（これを正文化せよ。独白は捨てよ）】\n{draft}\n\n"
            f"{instruction or ''}"
        ).strip()
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
    user_input: str = "",
) -> tuple[dict, Optional[str]]:
    """memory_inject をスコープ付き KV に合わせて正規化し、注入テキストを返す。

    Executor への注入は次のいずれかでのみ許可:
    - 明示的な記憶参照（「記憶を使って」/ use my memory 等）
    - 保有・ポジション・含み等の文脈
    - 保存済みのスコープ付き継続許可（例: 子どもに触れたら記憶を使ってよい / when I mention my kid）
    - 家族フラグ付きスロット（妻/子ども/wife/kids の話題、家族で旅行 / family trip）
    ニュース・おまかせ開発・単なる旅の相談では家族記憶を落とす。
    """
    from app.core.memory_policy import (
        family_topic_allows_use,
        memory_personalization_denied,
        standing_grant_allows_use,
        user_allows_memory_use,
        user_in_holdings_context,
    )

    if not filtered_kv_text:
        if supervisor_json.get("memory_inject"):
            logger.warning("memory_inject=true を拒否（スコープ内の記憶なし）")
        supervisor_json["memory_inject"] = False
        return supervisor_json, None

    denied = memory_personalization_denied(user_input)
    allowed = user_allows_memory_use(user_input) or user_in_holdings_context(user_input)
    if not denied:
        allowed = (
            allowed
            or standing_grant_allows_use(user_input, filtered_kv_text)
            or family_topic_allows_use(user_input, filtered_kv_text)
        )
    if allowed:
        supervisor_json["memory_inject"] = True
        return supervisor_json, filtered_kv_text

    if supervisor_json.get("memory_inject"):
        logger.warning(
            "memory_inject=true を拒否（明示記憶参照/保有文脈/継続許可なし — ニュース質問の保有パーソナライズ防止）"
        )
        supervisor_json["memory_inject"] = False
    return supervisor_json, None


def note_search_inject(search_results_text: Optional[str], supervisor_json: dict) -> Optional[str]:
    """検索結果があれば常に注入（search_used 自己申告を信用しない）。"""
    if search_results_text and not supervisor_json.get("search_used"):
        logger.info("📎 search_used=false だが検索結果が存在するため Executor へ注入します")
    return search_results_text


def should_emit_reasoning(mode: str) -> bool:
    """hearing / spec では reasoning SSE を出さない（開発ヒアリングの独白汚染防止）。"""
    return mode not in ("hearing", "spec_generation")


def _looks_like_spec_markdown(text: str) -> bool:
    """ユーザー向け仕様書（見出し・箇条書き）か。監督独白との切り分け用。"""
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"(?m)^#{1,3}\s+\S", t):
        return True
    if len(t) >= 240 and t.count("\n") >= 3:
        return any(k in t for k in ("対象", "プラットフォーム", "機能", "仕様", "Acceptance"))
    return False


def _is_internal_hearing_text(text: str) -> bool:
    """監督のモード議論・JSON設計がユーザー本文に混ざったか。"""
    t = (text or "").strip()
    if not t:
        return False
    if _looks_like_spec_markdown(t):
        return False
    if _HEARING_META_RE.search(t):
        return True
    try:
        from app.core.fact_filters.markup import looks_like_supervisor_dump

        if looks_like_supervisor_dump(t):
            return True
    except Exception:
        pass
    return False


def _resolve_spec_surface(supervisor_json: dict) -> str:
    """surface が空／独白でも、internal や文字列の spec_document から本文を拾う。"""
    spec = (supervisor_json or {}).get("spec_document")
    surface = ""
    internal = ""
    if isinstance(spec, str):
        surface = spec.strip()
    elif isinstance(spec, dict):
        surface = str(spec.get("surface") or "").strip()
        internal = str(spec.get("internal") or "").strip()
    for candidate in (surface, internal):
        if candidate and not _is_internal_hearing_text(candidate):
            return candidate
        if _looks_like_spec_markdown(candidate):
            return candidate
    return ""


def _sanitize_hearing_question(text: str) -> str:
    """next_question に思考全文が載ったとき、末尾の質問文だけ残す。"""
    t = (text or "").strip()
    if not t:
        return _HEARING_QUESTION_FALLBACK
    if not (_is_internal_hearing_text(t) or len(t) > 400):
        return t
    candidates = re.findall(r"[^。\n]{8,240}[？?]", t)
    for q in reversed(candidates):
        q = q.strip()
        if q and not _is_internal_hearing_text(q):
            return q
    return _HEARING_QUESTION_FALLBACK


def extract_supervisor_search_queries(supervisor_json: dict) -> list[str]:
    """hearing が Executor を飛ばすため、委譲用 <search> を拾って先に実行する。"""
    blobs: list[str] = []
    instruction = (supervisor_json or {}).get("instruction") or {}
    if isinstance(instruction, dict):
        for key in ("facts_to_present", "verified_facts", "unverified_facts", "logical_order"):
            for item in instruction.get(key) or []:
                if isinstance(item, str):
                    blobs.append(item)
    elif isinstance(instruction, str):
        blobs.append(instruction)
    hearing = (supervisor_json or {}).get("hearing_state") or {}
    if isinstance(hearing, dict):
        blobs.append(str(hearing.get("next_question") or ""))
        blobs.append(str(hearing.get("answer_preamble") or ""))
    found: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        for m in _SEARCH_QUERY_RE.finditer(blob):
            q = (m.group(1) or "").strip()
            if q and q not in seen:
                seen.add(q)
                found.append(q)
    return found[:4]


def _user_facing_facts(supervisor_json: dict, *, limit: int = 6) -> list[str]:
    """facts_to_present 等からユーザーに見せてよい短文だけ抽出。"""
    instruction = supervisor_json.get("instruction") or {}
    raw: list[Any] = []
    if isinstance(instruction, dict):
        for key in ("facts_to_present", "verified_facts", "unverified_facts"):
            vals = instruction.get(key) or []
            if isinstance(vals, list):
                raw.extend(vals)
    elif isinstance(instruction, str) and instruction.strip():
        raw.append(instruction.strip())

    hearing = supervisor_json.get("hearing_state") or {}
    if isinstance(hearing, dict):
        preamble = (hearing.get("answer_preamble") or "").strip()
        if preamble:
            raw.insert(0, preamble)

    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        if _FACT_SKIP_RE.search(text) or _is_internal_hearing_text(text):
            continue
        if len(text) > 500:
            text = text[:497] + "…"
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def compose_hearing_user_text(supervisor_json: dict) -> str:
    """hearing の Executor 下書き／空応答フォールバック。最終本文の正ではない。"""
    hearing = supervisor_json.get("hearing_state") or {}
    next_q = ""
    if isinstance(hearing, dict):
        next_q = (hearing.get("next_question") or "").strip()
    next_q = _sanitize_hearing_question(next_q)

    facts = _user_facing_facts(supervisor_json)
    parts: list[str] = []
    if facts:
        parts.append("\n".join(facts))
    parts.append(next_q)
    return "\n\n".join(parts)


def compose_spec_user_text(supervisor_json: dict) -> str:
    """spec の Executor 下書き／空応答フォールバック。最終本文の正ではない。"""
    surface = _resolve_spec_surface(supervisor_json)
    if not surface:
        surface = "仕様書ができました。"

    facts = [
        f
        for f in _user_facing_facts(supervisor_json, limit=4)
        if "未検証" not in f and "学習データに基づく仮説" not in f
    ]
    if not facts:
        return surface
    return "\n\n".join(["\n".join(facts), surface])


def is_continuation_utterance(user_input: str) -> bool:
    """未完了作業の再開指示か（プラン承認と分離する）。"""
    text = (user_input or "").strip()
    if not text:
        return False
    for pat in _CONTINUATION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def is_spec_approval_utterance(user_input: str) -> bool:
    """仕様書提示後の短い承認・着手指示か。"""
    text = (user_input or "").strip()
    if not text or len(text) > 40:
        return False
    if is_continuation_utterance(text):
        return False
    for pat in _SPEC_APPROVAL_PATTERNS:
        if re.fullmatch(pat, text, re.IGNORECASE):
            return True
    return False


def is_plan_approval_utterance(user_input: str) -> bool:
    """pending_plan 承認か。部分一致禁止（「続きを作成して」誤ヒット防止）。"""
    text = (user_input or "").strip()
    if not text or len(text) > 40:
        return False
    if is_continuation_utterance(text):
        return False
    for pat in _PLAN_APPROVAL_PATTERNS:
        if re.fullmatch(pat, text, re.IGNORECASE):
            return True
    return False


def last_assistant_supervisor_mode(messages: list[dict] | None) -> str | None:
    """直近アシスタントの thinking_json.mode を返す。"""
    if not messages:
        return None
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        raw = msg.get("thinking_json")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if isinstance(parsed, dict) and parsed.get("mode"):
            return str(parsed["mode"])
    return None


def extract_last_spec_document(messages: list[dict] | None) -> dict | None:
    """直近の spec_document（internal 優先）を履歴から取得。"""
    if not messages:
        return None
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        raw = msg.get("thinking_json")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        spec = parsed.get("spec_document")
        if isinstance(spec, dict) and (spec.get("internal") or spec.get("surface")):
            return spec
    return None


def _plan_from_spec(spec: dict | None) -> str:
    if not spec:
        return (
            "## 実装プラン\n"
            "1. 直前の仕様書（Acceptance 含む）に沿って実装する\n"
            "2. ビルドを通す\n"
            "3. Acceptance 未達項目を埋める\n"
        )
    surface = (spec.get("surface") or "").strip()
    internal = (spec.get("internal") or "").strip()
    summary = surface[:800] if surface else internal[:800]
    return (
        "## 実装プラン（仕様承認済み）\n\n"
        f"{summary}\n\n"
        "上記仕様と Acceptance チェックリストに従い、ファイル作成→ビルド確認→未達項目の解消の順で進める。"
    )


def apply_post_spec_approval_gate(
    user_input: str,
    mode: str,
    supervisor_json: dict,
    messages: list[dict] | None = None,
) -> tuple[str, dict]:
    """直近が spec_generation でユーザーが承認した場合、再 spec を禁止し plan へ誘導。"""
    if last_assistant_supervisor_mode(messages) != "spec_generation":
        return mode, supervisor_json
    if not is_spec_approval_utterance(user_input):
        return mode, supervisor_json

    # task / coding へ既に進んでいるなら尊重（再specだけ潰す）
    if mode in ("task", "coding"):
        logger.info("Spec承認検知: mode=%s を維持（再specなし）", mode)
        supervisor_json["mode"] = mode
        return mode, supervisor_json

    if mode in ("spec_generation", "hearing") or not supervisor_json.get("plan"):
        prev_spec = extract_last_spec_document(messages)
        if isinstance(supervisor_json.get("spec_document"), dict) and (
            supervisor_json["spec_document"].get("internal")
            or supervisor_json["spec_document"].get("surface")
        ):
            # 今回また仕様を出そうとしている場合は前回分を優先（ループ防止）
            prev_spec = prev_spec or supervisor_json.get("spec_document")

        logger.warning("Spec承認後の再spec/hearing禁止 → chat+plan に強制転換")
        mode = "chat"
        supervisor_json["mode"] = "chat"
        supervisor_json["hearing_state"] = None
        supervisor_json["spec_document"] = prev_spec
        if not supervisor_json.get("plan"):
            supervisor_json["plan"] = _plan_from_spec(prev_spec)
        inst = supervisor_json.get("instruction")
        if not isinstance(inst, dict):
            inst = {}
        facts = list(inst.get("facts_to_present") or [])
        note = "ユーザーが直前の仕様書を承認した。再ヒアリング・再仕様書は禁止。提示プランのYes/No確認のみ。"
        if note not in facts:
            facts.insert(0, note)
        inst["facts_to_present"] = facts
        supervisor_json["instruction"] = inst

    return mode, supervisor_json
