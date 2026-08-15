"""
グラウンディング統合パイプライン。

正規表現パッチを個別に増やすのではなく、この1関数経由で後処理する。
引用契約（citation）が代替できるフィルタは CONSOLIDATION_NOTES に記録し、
段階的に薄くしていく。
"""
from __future__ import annotations

from typing import Callable

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 引用契約で代替済み / 縮小予定のフィルタ（削除は eval 全パス後）
CONSOLIDATION_NOTES = {
    "verify_temporal_leadership_claims": "partial→citation.verify_citations (known risky names)",
    "verify_numbers_exist_in_source": "partial→citation absolute-number disclaimer",
    "strip_excuse_hallucinations": "kept (orthogonal to citations)",
    "trim_incomplete_trailing_sentence": "kept (truncation, not grounding)",
    # 2026-08: supervisor.filter_fact から pipeline 重複ステップを外し、
    # 最終本文 grounding は finalize の本関数のみに一本化。
    "supervisor_filter_fact": "light hygiene only; full pass = apply_grounding_pipeline",
}


def _run_step(name: str, before: str, produce: Callable[[], str]) -> str:
    from .filter_metrics import track_filter

    after = produce()
    if not isinstance(after, str):
        after = str(after or "")
    return track_filter(name, before, after)


def apply_grounding_pipeline(
    text: str,
    source_text: str = "",
    user_input: str = "",
) -> str:
    """Executor最終出力に対する統合グラウンディング後処理。"""
    if not text:
        return text

    from .currency import check_currency_consistency
    from .financial import (
        verify_numbers_exist_in_source,
        soften_ungrounded_earnings_timing,
        correct_jp_session_price_labels,
        soften_stale_night_futures_claims,
        soften_us_morning_wrap_as_close,
    )
    from .temporal import (
        verify_chronological_rationalization,
        strip_outdated_past_event_predictions,
        strip_out_of_period_event_mentions,
        verify_holiday_and_weekend_claims,
        strip_unverified_day_of_week,
        fix_relative_date_labels,
    )
    from .entity import (
        verify_temporal_leadership_claims,
        filter_unknown_entity_listings,
        deduplicate_spot_listings,
        verify_exit_and_address_entanglement,
    )
    from .safety import (
        sanitize_buffer_contamination,
        sanitize_internal_tool_mentions,
        enforce_variable_numerical_claims,
    )
    from .markup import strip_internal_markup
    from .format import (
        correct_common_typos,
        strip_unrequested_memory_mentions,
        strip_unrequested_child_ask,
        strip_omakase_skill_questions,
        strip_unrequested_yahoo_finance,
        clean_broken_markdown_tables,
        strip_excuse_hallucinations,
        strip_false_user_attribution,
        trim_incomplete_trailing_sentence,
        strip_dangling_tool_promises,
        ensure_markdown_block_breaks,
    )
    from .citation import verify_citations, reset_citation_metrics, record_trim_metric
    from .filter_metrics import persist_filter_metrics

    reset_citation_metrics()
    before_all = text
    src = source_text or ""
    ui = user_input or ""

    text = _run_step("strip_internal_markup", text, lambda: strip_internal_markup(text))
    text = _run_step(
        "check_currency_consistency",
        text,
        lambda: check_currency_consistency(text)[1],
    )
    text = _run_step(
        "verify_numbers_exist_in_source",
        text,
        lambda: verify_numbers_exist_in_source(text, src)[1],
    )
    # レガシー: 役職ハルシネーション（citation と併用、段階的縮小）
    text = _run_step(
        "verify_temporal_leadership_claims",
        text,
        lambda: verify_temporal_leadership_claims(text, src),
    )
    text = _run_step(
        "verify_chronological_rationalization",
        text,
        lambda: verify_chronological_rationalization(text, src),
    )
    text = _run_step(
        "filter_unknown_entity_listings",
        text,
        lambda: filter_unknown_entity_listings(text),
    )
    text = _run_step(
        "enforce_variable_numerical_claims",
        text,
        lambda: enforce_variable_numerical_claims(text, src, user_input=ui),
    )
    text = _run_step("correct_common_typos", text, lambda: correct_common_typos(text))
    text = _run_step(
        "strip_unrequested_memory_mentions",
        text,
        lambda: strip_unrequested_memory_mentions(text, user_input=ui),
    )
    text = _run_step(
        "strip_unrequested_child_ask",
        text,
        lambda: strip_unrequested_child_ask(text, user_input=ui),
    )
    text = _run_step(
        "strip_omakase_skill_questions",
        text,
        lambda: strip_omakase_skill_questions(text, user_input=ui),
    )
    text = _run_step(
        "strip_unrequested_yahoo_finance",
        text,
        lambda: strip_unrequested_yahoo_finance(text, user_input=ui),
    )
    text = _run_step(
        "strip_outdated_past_event_predictions",
        text,
        lambda: strip_outdated_past_event_predictions(text),
    )
    text = _run_step(
        "deduplicate_spot_listings",
        text,
        lambda: deduplicate_spot_listings(text),
    )
    text = _run_step(
        "verify_exit_and_address_entanglement",
        text,
        lambda: verify_exit_and_address_entanglement(text),
    )
    text = _run_step(
        "sanitize_internal_tool_mentions",
        text,
        lambda: sanitize_internal_tool_mentions(text),
    )
    text = _run_step(
        "clean_broken_markdown_tables",
        text,
        lambda: clean_broken_markdown_tables(text),
    )
    text = _run_step(
        "strip_out_of_period_event_mentions",
        text,
        lambda: strip_out_of_period_event_mentions(text),
    )
    text = _run_step(
        "verify_holiday_and_weekend_claims",
        text,
        lambda: verify_holiday_and_weekend_claims(text),
    )
    text = _run_step(
        "fix_relative_date_labels",
        text,
        lambda: fix_relative_date_labels(text),
    )
    text = _run_step(
        "strip_excuse_hallucinations",
        text,
        lambda: strip_excuse_hallucinations(text),
    )
    text = _run_step(
        "strip_false_user_attribution",
        text,
        lambda: strip_false_user_attribution(text, user_input=ui),
    )
    text = _run_step(
        "soften_ungrounded_earnings_timing",
        text,
        lambda: soften_ungrounded_earnings_timing(text, src),
    )
    text = _run_step(
        "correct_jp_session_price_labels",
        text,
        lambda: correct_jp_session_price_labels(text, src),
    )
    text = _run_step(
        "soften_stale_night_futures_claims",
        text,
        lambda: soften_stale_night_futures_claims(text, src),
    )
    text = _run_step(
        "soften_us_morning_wrap_as_close",
        text,
        lambda: soften_us_morning_wrap_as_close(text, src),
    )
    text = _run_step(
        "sanitize_buffer_contamination",
        text,
        lambda: sanitize_buffer_contamination(text),
    )
    text = _run_step(
        "strip_unverified_day_of_week",
        text,
        lambda: strip_unverified_day_of_week(
            text, source_text=src, strip_if_no_source=True
        ),
    )

    # 中核: 引用契約
    text = _run_step("verify_citations", text, lambda: verify_citations(text, src))
    text = _run_step(
        "ensure_markdown_block_breaks",
        text,
        lambda: ensure_markdown_block_breaks(text),
    )
    text = _run_step(
        "strip_dangling_tool_promises",
        text,
        lambda: strip_dangling_tool_promises(text),
    )
    text = _run_step(
        "trim_incomplete_trailing_sentence",
        text,
        lambda: trim_incomplete_trailing_sentence(text),
    )

    if text != before_all:
        record_trim_metric(True)
    try:
        persist_filter_metrics()
    except Exception:
        pass
    return text
