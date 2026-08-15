import re
from datetime import date, timedelta
from typing import Optional
from app.utils.logger import get_logger
from app.core.source_evaluator import verify_entity_claim_attribution

logger = get_logger(__name__)

from .currency import *
from .financial import *
from .temporal import *
from .safety import *
from .entity import *
from .format import *
from .citation import *
from .markup import strip_internal_markup, looks_incomplete_output, sanitize_preserving_body
from .pipeline import apply_grounding_pipeline, CONSOLIDATION_NOTES


def filter_fact(fact: str) -> str:
    """
    Supervisor 向けの軽い instruction hygiene。

    重いグラウンディング（役職・時系列・曜日・未知エンティティ等）は
    finalize の apply_grounding_pipeline に一本化する。ここでは executor に
    渡す前に潰したい助言・数値制限・主体取り違えだけを残す。
    """
    fact = correct_common_typos(fact)
    # 複数主体における主語・主張の取り違え（instruction 段階で潰す価値が高い）
    _, fact = verify_entity_claim_attribution(fact)
    fact = verify_action_modality_consistency(fact)

    # 数値制限の隠蔽
    if NUMERIC_LIMITS_PATTERN.search(fact):
        fact = NUMERIC_LIMITS_PATTERN.sub("（※具体的な数値・制限は公式サイトをご確認ください）", fact)

    # 🟠 P1: 投資助言・確度数値化・手法誘導の抑制
    if ADVICE_PATTERN.search(fact):
        fact = ADVICE_PATTERN.sub("（※具体的な売買判断・資金配分・自信度の断定は控えます）", fact)

    # 🔴 P0: 未検証情報や見た目の強さ（◯△❌記号や断言）の制御
    if SYMBOL_TABLE_PATTERN.search(fact) and "これは学習データに基づく仮説" not in fact:
        fact = f'⚠️ **【学習データに基づく仮説・現時点未検証】** {fact}'

    # 🟢 P3: 二次ソース言及時の明示
    if any(kw in fact for kw in ["まとめサイト", "ブログ", "噂", "SNS", "掲示板", "二次情報"]) and "※二次ソースのみ確認" not in fact:
        fact += " (※二次ソースのみ確認)"

    # 不確実性バッジ（強いキーワードのみ）
    if "unconfirmed-badge" not in fact and "⚠️ **[未確認]**" not in fact and "⚠️[未確認]" not in fact and "学習データに基づく仮説" not in fact:
        if any(kw in fact for kw in ["未確認", "未検証", "噂され"]):
            fact = f'⚠️ **[未確認]** {fact}'

    # 外貨の勝手な大口円換算・他通貨並記の削除（ドル円スポットは消さない）
    fact = strip_unauthorized_jpy_conversions(fact)

    return fact


def filter_facts_to_present(facts: list[str]) -> list[str]:
    """
    supervisor の facts_to_present 向け軽量フィルタ。
    最終本文の grounding は finalize.apply_grounding_pipeline が担当する。
    """
    if not facts:
        return []
    return [filter_fact(f) for f in facts]



def enforce_persona_fact_separation(persona_text: str, verified_facts: list[str], user_input: Optional[str] = None) -> str:
    """
    ペルソナ層とファクト層の分離（supervisor/executor構造の応用）：
    口調レイヤー（関西弁やキャラノリ）が新しい数量情報を勝手に盛ったり追加するのを防ぎ、
    検証済みファクト層に存在する数値以外の大きなハルシネーション数字を抑制・検知する。
    """
    _, validated_text = check_currency_consistency(persona_text)
    validated_text = correct_common_typos(validated_text)
    source_context = " ".join(verified_facts) if verified_facts else None
    validated_text = strip_unverified_day_of_week(validated_text, source_text=source_context, strip_if_no_source=False)
    validated_text = strip_unrequested_memory_mentions(validated_text, user_input=user_input)
    validated_text = strip_unrequested_child_ask(validated_text, user_input=user_input)
    from .format import strip_omakase_skill_questions
    validated_text = strip_omakase_skill_questions(validated_text, user_input=user_input)
    validated_text = strip_unrequested_yahoo_finance(validated_text, user_input=user_input)
    validated_text = strip_outdated_past_event_predictions(validated_text)
    validated_text = verify_action_modality_consistency(validated_text, source_text=source_context)
    validated_text = verify_actual_vs_guidance_hallucination(validated_text, source_text=source_context)
    validated_text = deduplicate_spot_listings(validated_text)
    validated_text = verify_exit_and_address_entanglement(validated_text)
    validated_text = sanitize_internal_tool_mentions(validated_text)
    validated_text = clean_broken_markdown_tables(validated_text)
    validated_text = strip_out_of_period_event_mentions(validated_text)
    validated_text = verify_maintenance_date_relevance(validated_text, source_text=source_context, user_input=user_input)
    validated_text = verify_holiday_and_weekend_claims(validated_text)
    validated_text = strip_excuse_hallucinations(validated_text)
    return validated_text

