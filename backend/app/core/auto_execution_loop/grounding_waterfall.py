"""
Post-loop grounding waterfall (dsh-inspired named stage).

Contract (production log == screenshot before/after):
  assistant/message  ->  grounding/apply  (pipeline)  with grounding/before|after

The agent loop only produces candidate text. Grounding is a separate stage
outside the tool/LLM loop body — same shape as dsh tools/pre|post-execute.
"""
from __future__ import annotations

from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


def apply_grounding_stage(
    text: str,
    *,
    search_results: Optional[str] = None,
    user_input: str = "",
    session_id: str = "",
) -> str:
    """
    Run the grounding pipeline as a named post-loop stage.

    Emits session events when session_id is set:
      - assistant/message
      - grounding/apply (phase=start)
      - grounding/before
      - grounding/after
    """
    from app.core.fact_filters.markup import sanitize_preserving_body, strip_internal_markup
    from app.core.fact_filters.pipeline import apply_grounding_pipeline
    from app.core.session_events import append_event, truncate_text

    pre = text or ""
    sid = (session_id or "").strip()

    if sid:
        append_event(
            sid,
            "assistant/message",
            {"text": truncate_text(pre), "role": "assistant"},
        )
        append_event(sid, "grounding/apply", {"phase": "start"})
        append_event(
            sid,
            "grounding/before",
            {
                "text": truncate_text(pre),
                "user_input": truncate_text(user_input or "", 500),
            },
        )

    def _run_pipeline(t: str) -> str:
        return apply_grounding_pipeline(
            t, str(search_results or ""), user_input=user_input or ""
        )

    try:
        after = sanitize_preserving_body(pre, _run_pipeline)
    except Exception as e:
        logger.warning("grounding/apply failed: %s", e)
        after = strip_internal_markup(pre)

    if sid:
        append_event(
            sid,
            "grounding/after",
            {
                "text": truncate_text(after),
                "changed": (after or "") != (pre or ""),
            },
        )
        append_event(
            sid,
            "grounding/apply",
            {
                "phase": "complete",
                "changed": (after or "") != (pre or ""),
            },
        )

    return after
