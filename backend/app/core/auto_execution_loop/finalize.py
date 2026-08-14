"""Post-loop synthesis, sanitization, and grounding."""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from app.utils.logger import get_logger
from .helpers import (
    clear_ui_with_progress,
    snapshot_visible,
    ui_progress,
)

logger = get_logger(__name__)


def _run_executor(*args, **kwargs):
    """Resolve via loop module so patches on loop.run_executor still apply."""
    from app.core.auto_execution_loop import loop as loop_mod

    return loop_mod.run_executor(*args, **kwargs)


async def finalize_loop_response(
    *,
    user_input: str,
    instruction: str,
    executor_sys_prompt: str,
    mode: str,
    search_results: Optional[str],
    memory_text: Optional[str],
    exec_history: list,
    loop_history: list,
    tool_handler: Any,
    final_accumulated_response: str,
    force_tool_synthesis: bool,
    last_good_user_visible: str,
    continuation_attempted: bool,
    yield_sse_func: Optional[Callable] = None,
) -> tuple[str, str]:
    """Return (final_response, tool_results_summary)."""
    tool_results_summary = "\n".join(tool_handler.tool_results) if tool_handler.tool_results else ""
    # 重複停止などで search_results にマージ済みでも、summary が空なら再構築
    if not tool_results_summary and search_results and force_tool_synthesis:
        tool_results_summary = search_results

    from app.core.fact_filters.markup import (
        looks_like_tool_dump,
        strip_tool_dump_blocks,
        strip_internal_markup,
        normalize_final_answer_body,
    )

    # Normalize FINAL_ANSWER before empty/synth decisions (marker-only must count as empty)
    _body, _empty_marker = normalize_final_answer_body(final_accumulated_response)
    if _empty_marker:
        final_accumulated_response = ""
        force_tool_synthesis = True
    elif "<<<FINAL_ANSWER>>>" in (final_accumulated_response or ""):
        final_accumulated_response = _body

    # 空本文ガード: pipeline 前に last_good を優先復元（ツール生ダンプは復元しない）
    if not final_accumulated_response.strip() and not force_tool_synthesis:
        if last_good_user_visible.strip() and not looks_like_tool_dump(last_good_user_visible):
            logger.warning("⚠️ 最終応答が空のため last_good_user_visible を復元します")
            final_accumulated_response = last_good_user_visible
        else:
            for msg in reversed(loop_history):
                if msg.get("role") == "assistant" and msg.get("content"):
                    clean_content = snapshot_visible(msg["content"])
                    if clean_content and not looks_like_tool_dump(clean_content):
                        final_accumulated_response = clean_content
                        break

    def _synth_system_prompt(extra: str) -> str:
        """Synthesis must NOT inherit FINAL_ANSWER boundary (it causes empty-body loops)."""
        base = executor_sys_prompt or ""
        # Drop conflicting boundary rules from the main executor prompt
        base = re.sub(
            r"【構造的モダリティ分離（出力境界トークン）の厳守ルール】[\s\S]*?"
            r"(?=【|\Z)",
            "",
            base,
            count=1,
        )
        base = base.replace("<<<FINAL_ANSWER>>>", "")
        return (
            base
            + "\n\n# Synthesis mode\n"
            "Write the user-facing answer directly in plain prose/markdown.\n"
            "Do NOT output <<<FINAL_ANSWER>>>, <think>, tool XML, or planning notes.\n"
            + (extra or "")
        )

    def _extract_synth_text(rebuilt: str) -> str:
        from app.core.fact_filters.markup import (
            strip_internal_markup,
            strip_meta_reasoning_preamble,
            split_final_answer,
        )

        def _finalize(t: str) -> str:
            return strip_meta_reasoning_preamble(t)

        body, empty_m = normalize_final_answer_body(rebuilt)
        if empty_m:
            pre, _, _ = split_final_answer(rebuilt)
            cleaned = strip_internal_markup(pre).strip()
            if len(cleaned) >= 80:
                logger.warning(
                    "⚠️ Synth returned empty FINAL_ANSWER body; using cleaned preamble"
                )
                return _finalize(cleaned)
            cleaned_all = strip_internal_markup(rebuilt).strip()
            return _finalize(cleaned_all)
        if "<<<FINAL_ANSWER>>>" in (rebuilt or ""):
            return _finalize(strip_internal_markup(body).strip())
        return _finalize(strip_internal_markup(rebuilt).strip())

    async def _synthesize_from_tools(prompt: str, sys_extra: str) -> str:
        rebuilt = ""
        s_stream = _run_executor(
            user_input=prompt,
            instruction=instruction,
            search_results=search_results or tool_results_summary,
            memory_text=memory_text,
            history_messages=exec_history[-4:] if exec_history else [],
            mode=mode,
            system_instruction=_synth_system_prompt(sys_extra),
        )
        async for chunk in s_stream:
            rebuilt += chunk
            # Stream only post-strip deltas would be complex; emit raw then UI clear on done
            if yield_sse_func:
                yield_sse_func({"type": "chunk", "content": chunk})
        # 合成パスもトークン上限で切断されうる。途中切れ検知時は1回だけ継続生成する
        from app.core.fact_filters.markup import looks_incomplete_output
        if looks_incomplete_output(rebuilt):
            logger.info("🔄 合成回答の途中切れを検知したため継続生成を1回試みます")
            try:
                cont_prompt = (
                    "直前の回答が途中で切れています。続きの文章のみを出力してください。"
                    "Markdown表の途中ならセルを完成させて表を閉じてください。"
                    "前文の繰り返し・XMLツールタグ・thinkタグは禁止です。"
                )
                cont_history = (exec_history[-4:] if exec_history else []) + [
                    {"role": "assistant", "content": strip_internal_markup(rebuilt)},
                    {"role": "user", "content": cont_prompt},
                ]
                cont_stream = _run_executor(
                    user_input=cont_prompt,
                    instruction=instruction,
                    search_results=search_results or tool_results_summary,
                    memory_text=memory_text,
                    history_messages=cont_history,
                    mode=mode,
                    system_instruction=_synth_system_prompt(sys_extra),
                    enable_thinking=False,
                )
                cont_buf = ""
                async for chunk in cont_stream:
                    cont_buf += chunk
                continuation = strip_internal_markup(cont_buf)
                if continuation.strip():
                    rebuilt = rebuilt.rstrip() + "\n" + continuation
                    if yield_sse_func:
                        yield_sse_func({"type": "chunk", "content": "\n" + continuation})
            except Exception as e:
                logger.warning(f"Synth continuation failed: {e}")
        return _extract_synth_text(rebuilt)

    def _deterministic_tool_fallback() -> str:
        """Last resort when LLM synthesis fails — never return empty if we have data."""
        blob = (tool_results_summary or "") + "\n" + (search_results or "")
        # Pull a few quote-ish lines if present
        lines = []
        for line in blob.splitlines():
            s = line.strip()
            if not s:
                continue
            if any(
                k in s
                for k in (
                    "ticker",
                    "current_price",
                    "previous_close",
                    "change_pct",
                    "^GSPC",
                    "^DJI",
                    "^IXIC",
                    "Dow",
                    "S&P",
                    "Nasdaq",
                )
            ):
                lines.append(s)
            if len(lines) >= 12:
                break
        head = "\n".join(lines[:12]) if lines else blob[:1200].strip()
        return (
            "I gathered market data for your question, but the final write-up step failed. "
            "Here are the key tool/search snippets — ask me to summarize again if needed:\n\n"
            f"{head}"
        )

    need_synth = (
        force_tool_synthesis or not final_accumulated_response.strip()
    ) and bool(tool_results_summary or search_results)
    if need_synth:
        logger.info("⚠️ ツール実行後に最終回答が未生成だったため、ツール結果をもとに集約回答を生成します")
        clear_ui_with_progress(yield_sse_func, ui_progress("compose_from_search"))
        try:
            from app.core.completion_status import wants_code_in_chat
            code_hint = ""
            if wants_code_in_chat(user_input):
                code_hint = (
                    "ユーザーはコード全文をチャットで求めている。"
                    "「作成完了」だけの報告は禁止。パス・要点のあとコード全文をフェンスで出せ。"
                )
            final_prompt_msg = (
                "検索結果・ツール実行結果を踏まえて、ユーザーの質問に対する最終回答を自然な文章で作成してください。"
                "XMLタグや生ログ（[Local Tool:…]【一般検索結果】【引用契約】等）はそのまま出力せず、整理して回答してください。"
                "ファイルを作成した場合はパスと要点を必ず含めてください。"
                "Do not output <<<FINAL_ANSWER>>> or long internal planning notes—write the answer only."
                + code_hint
            )
            final_accumulated_response = await _synthesize_from_tools(
                final_prompt_msg,
                "\n\n【重要】XMLタグやツールタグ・ツール生ログは一切出力しないでください。"
                "結果を踏まえた最終的な回答のみを自然な対話で出力すること。メタ完了宣言だけで終わらないこと。"
                "<<<FINAL_ANSWER>>> は出力禁止。",
            )
        except Exception as e:
            logger.error(f"Final synthesis error: {e}")
            final_accumulated_response = ""

    # 空洞完了（「ファイル作成完了」だけ等）→ 1回だけ本体合成
    try:
        from app.core.completion_status import is_hollow_completion, wants_code_in_chat
        if (
            is_hollow_completion(final_accumulated_response, user_input)
            and (tool_results_summary or search_results)
        ):
            logger.warning("⚠️ 空洞完了を検知したため、本体回答を再合成します")
            clear_ui_with_progress(
                yield_sse_func, "Rewriting a full answer from tool results…"
            )
            hollow_prompt = (
                "The previous response had no usable user-facing body. "
                "Using only the search/tool results, write a complete market answer now. "
                "No <<<FINAL_ANSWER>>>, no <think>, no tool XML."
            )
            if wants_code_in_chat(user_input):
                hollow_prompt += " Include full code in fences."
            rebuilt = await _synthesize_from_tools(
                hollow_prompt,
                "\nメタ完了禁止。XMLツールタグ禁止。本文を書け。<<<FINAL_ANSWER>>>禁止。",
            )
            if rebuilt.strip() and not is_hollow_completion(rebuilt, user_input):
                final_accumulated_response = rebuilt
            elif rebuilt.strip() and len(rebuilt) > len(final_accumulated_response or ""):
                final_accumulated_response = rebuilt
    except Exception as e:
        logger.warning(f"Hollow completion rebuild failed: {e}")

    if not final_accumulated_response.strip():
        if (
            last_good_user_visible.strip()
            and not looks_like_tool_dump(last_good_user_visible)
        ):
            final_accumulated_response = last_good_user_visible
        elif tool_results_summary or search_results:
            final_accumulated_response = _deterministic_tool_fallback()
        else:
            final_accumulated_response = (
                "*(⚠️ Response generation failed or was filtered. Please try again.)*"
            )
            logger.warning("⚠️ 最終応答が空になったため、フォールバックメッセージを挿入しました。")

    # --- 物理分離構造パース: <<<FINAL_ANSWER>>> 以降を厳格抽出 ---
    if "<<<FINAL_ANSWER>>>" in final_accumulated_response:
        parts = final_accumulated_response.split("<<<FINAL_ANSWER>>>")
        final_accumulated_response = parts[-1].strip()

    from app.core.fact_filters.markup import (
        strip_internal_markup,
        strip_supervisor_dump,
        looks_like_supervisor_dump,
        looks_like_tool_dump,
        strip_tool_dump_blocks,
        looks_incomplete_output,
        sanitize_preserving_body,
    )
    final_accumulated_response = strip_internal_markup(final_accumulated_response)
    # 進捗プレースホルダを最終本文から除去
    final_accumulated_response = re.sub(r"(?m)^⏳[^\n]*\n?", "", final_accumulated_response)
    final_accumulated_response = re.sub(
        r"(?m)^(?:まず、ユーザーの発言を分析します[^\n]*\n+|Output format:[^\n]*\n+|user_intent_analysis:[^\n]*\n+)+",
        "",
        final_accumulated_response,
    )
    final_accumulated_response = strip_tool_dump_blocks(final_accumulated_response)
    if looks_like_supervisor_dump(final_accumulated_response):
        logger.warning("⚠️ 最終本文に Supervisor 独白を検出したため除去します")
        stripped_sup = strip_supervisor_dump(final_accumulated_response)
        # incomplete バナーだけは残す
        banner_m = re.search(
            r"\*\(\s*⚠️[^)]*(?:続きを作成して|未完了)[^)]*\)\*",
            final_accumulated_response,
        )
        if stripped_sup.strip() and not looks_like_supervisor_dump(stripped_sup):
            final_accumulated_response = stripped_sup
        elif banner_m:
            final_accumulated_response = banner_m.group(0)
        else:
            final_accumulated_response = (
                "*(作業中に内部メモが本文へ漏れました。状態を確認のうえ「続きを作成して」で再開してください)*"
            )

    # ツール生ダンプが残っていたら破棄して再合成（エコー対策）
    if looks_like_tool_dump(final_accumulated_response):
        logger.warning("⚠️ 最終本文にツール生ダンプを検出したため除去・再合成します")
        stripped = strip_tool_dump_blocks(final_accumulated_response)
        if looks_like_tool_dump(stripped) or len(stripped) < 20:
            final_accumulated_response = ""
            if tool_results_summary or search_results:
                try:
                    dump_prompt = (
                        "直前の出力にはツール生ログが含まれていました。"
                        "検索結果・ツール実行結果だけを根拠に、ユーザーへの最終回答を自然な文章で書いてください。"
                        "生ログ・XMLタグ・【引用契約】は出力禁止。"
                    )
                    rebuilt = await _synthesize_from_tools(
                        dump_prompt,
                        "\nメタ完了禁止。XMLツールタグ禁止。ツール生ログ禁止。本文を書け。",
                    )
                    if rebuilt.strip() and not looks_like_tool_dump(rebuilt):
                        final_accumulated_response = rebuilt
                    else:
                        final_accumulated_response = strip_tool_dump_blocks(rebuilt)
                except Exception as e:
                    logger.warning(f"Tool-dump resynthesis failed: {e}")
            if not final_accumulated_response.strip():
                final_accumulated_response = (
                    "作業結果はツール側に反映されましたが、チャット本文の生成に失敗しました。"
                    "「続きを本文に書いて」と送るか、作成ファイルのパスを指定してください。"
                )
        else:
            final_accumulated_response = stripped

    # 途切れ検知 → 1回だけ継続生成
    if looks_incomplete_output(final_accumulated_response) and not continuation_attempted:
        continuation_attempted = True
        logger.info("🔄 不完全出力を検知したため継続生成を1回試みます")
        try:
            cont_prompt = (
                "直前の回答が途中で切れています。続きの文章またはコードのみを出力してください。"
                "Markdown表の途中ならセルを完成させて表を閉じてください。"
                "前文の繰り返し・XMLツールタグ・thinkタグは禁止です。"
            )
            cont_history = exec_history + [
                {"role": "assistant", "content": final_accumulated_response},
                {"role": "user", "content": cont_prompt},
            ]
            cont_stream = _run_executor(
                user_input=cont_prompt,
                instruction=instruction,
                search_results=search_results,
                memory_text=memory_text,
                history_messages=cont_history,
                mode=mode,
                system_instruction=executor_sys_prompt + "\n続きのみ。ツールタグ・think禁止。表途中なら完成させよ。",
                enable_thinking=False,
            )
            continuation = ""
            cont_buf = ""
            async for chunk in cont_stream:
                cont_buf += chunk
                # 生チャンクを出さず、内部マークアップ除去後に差分だけ SSE
                cleaned = strip_internal_markup(cont_buf)
                if cleaned.startswith(continuation):
                    delta = cleaned[len(continuation):]
                else:
                    delta = cleaned
                    continuation = ""
                if delta:
                    continuation = cleaned
                    if yield_sse_func:
                        yield_sse_func({"type": "chunk", "content": delta})
            continuation = strip_internal_markup(cont_buf)
            if continuation.strip():
                final_accumulated_response = (
                    final_accumulated_response.rstrip() + "\n" + continuation
                )
        except Exception as e:
            logger.warning(f"Continuation generation failed: {e}")

    # Post-loop waterfall: assistant/message -> grounding/apply (before/after logged)
    pre_sanitize = final_accumulated_response
    try:
        from app.core.auto_execution_loop.grounding_waterfall import apply_grounding_stage

        _sid = getattr(tool_handler, "session_id", None) or ""
        final_accumulated_response = apply_grounding_stage(
            pre_sanitize,
            search_results=search_results,
            user_input=user_input or "",
            session_id=_sid,
        )
    except Exception as e:
        logger.warning(f"Fact filter validation warning in auto_execution_loop: {e}")
        final_accumulated_response = strip_internal_markup(pre_sanitize)

    if not final_accumulated_response.strip():
        if last_good_user_visible.strip() and not looks_like_tool_dump(last_good_user_visible):
            logger.warning("⚠️ サニタイズ後も空のため last_good_user_visible を復元します")
            final_accumulated_response = strip_internal_markup(last_good_user_visible)
        elif tool_results_summary or search_results:
            logger.warning("⚠️ サニタイズ後も空のため tool/search フォールバックを挿入します")
            final_accumulated_response = _deterministic_tool_fallback()
        else:
            final_accumulated_response = (
                "*(⚠️ Response generation failed or was filtered. Please try again.)*"
            )

    # 最終ガード: それでもダンプならフォールバック（生ログを返さない）
    if looks_like_tool_dump(final_accumulated_response):
        logger.warning("⚠️ 最終ガードでツール生ダンプを遮断しました")
        if tool_results_summary or search_results:
            final_accumulated_response = _deterministic_tool_fallback()
        else:
            final_accumulated_response = (
                "Tool results were collected, but the chat write-up failed. "
                "Please ask me to summarize again."
            )

    return final_accumulated_response.strip(), tool_results_summary

