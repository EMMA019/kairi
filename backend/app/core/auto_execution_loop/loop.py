import json
import re
import asyncio
import uuid
import time
from typing import AsyncGenerator, Optional
from datetime import datetime
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)

from app.core.tools.handler import ToolHandler
from app.core.llm_client import stream_model
from app.core.executor import run_executor
from app.routers.settings import get_settings

from .heuristics import _detect_test_failure, _detect_error, _detect_success
from .compression import _smart_compress_loop_history
from .supervisor import _analyze_with_supervisor
from .helpers import (
    clear_ui_with_progress as _clear_ui_with_progress,
    ensure_executor_guards,
    error_signature as _error_signature,
    remember_good as _remember_good,
    snapshot_visible as _snapshot_visible,
    ui_progress as _ui_progress,
)
from .stream_parse import (
    CLOSING_TAG as closing_tag_pattern,
    SELF_CLOSING as self_closing_pattern,
    TOOL_TAG_START as tool_tag_start_pattern,
    iter_executor_stream,
)
from .gate_helpers import (
    MAX_GATE_REINJECT,
    append_final_gate_banner,
    extract_spec_internal,
    gate_reinject_message as _gate_reinject_message,
    run_task_completion_gate,
)
from .finalize import finalize_loop_response


async def auto_execute_with_retry(
    user_input: str,
    instruction: str,
    supervisor_sys_prompt: str,
    supervisor_dynamic_sys: str,
    executor_sys_prompt: str,
    executor_dynamic_sys: str,
    mode: str,
    session_id: str,
    history_messages: list,
    search_results: Optional[str] = None,
    memory_text: Optional[str] = None,
    max_tool_loops: int = 40,
    max_supervisor_retries: int = 5,
    yield_sse_func=None,
) -> tuple[str, str, list]:
    """
    自律実行ループのメイン処理。
    
    Returns:
        (final_response, tool_results_summary, escalation_history)
    """
    loop_count = 0
    loop_history = []
    final_accumulated_response = ""
    last_good_user_visible = ""  # clear_buffer / 過剰掃除後の復元用
    continuation_attempted = False
    exec_history = history_messages
    escalation_history = []
    empty_result_retry_count = 0
    empty_output_retry_count = 0
    
    tool_handler = ToolHandler(
        session_id=session_id,
        mode=mode,
        allow_mocks="モック" in user_input or "ダミー" in user_input or "仮実装" in user_input,
    )
    try:
        from app.core.tools.repeat_reminder import reset_chain
        reset_chain(session_id)
    except Exception:
        pass
    try:
        from app.core.prompt_builder.skill_catalog import maybe_catalog_refresh_message
        _catalog_refresh = maybe_catalog_refresh_message(session_id, user_input)
        if _catalog_refresh:
            loop_history.append({"role": "user", "content": _catalog_refresh})
            instruction = (_catalog_refresh + "\n\n" + (instruction or "")).strip()
    except Exception:
        pass

    prev_goal = None
    this_run_gate_cap = MAX_GATE_REINJECT
    persist_gate = None  # type: ignore[assignment]
    try:
        from app.core.goal_state import (
            format_resume_instruction,
            is_blocked,
            latest_goal,
            persist_gate as _persist_gate,
            remaining_rounds,
        )
        from app.core.chat_orchestrator import is_continuation_utterance

        persist_gate = _persist_gate
        prev_goal = latest_goal(session_id)
        resume_goal = (
            prev_goal
            if is_continuation_utterance(user_input) and is_blocked(prev_goal)
            else None
        )
        if resume_goal:
            resume_msg = format_resume_instruction(resume_goal)
            loop_history.append({"role": "user", "content": resume_msg})
            instruction = (resume_msg + "\n\n" + (instruction or "")).strip()
            _remain = remaining_rounds(resume_goal)
            this_run_gate_cap = min(MAX_GATE_REINJECT, _remain)
            logger.info(
                "goal resume session=%s reasons=%s remain=%s gate_cap=%s",
                (session_id or "")[:16],
                resume_goal.get("reasons"),
                _remain,
                this_run_gate_cap,
            )
    except Exception as e:
        logger.debug("goal resume skipped: %s", e)
    
    # ワークスペースパスの解決
    try:
        from app.routers.workspace import get_workspace_dir
        ws_dir = str(get_workspace_dir())
    except Exception:
        from pathlib import Path
        ws_dir = str(Path(__file__).parent.parent.parent / "workspace")
    
    executed_tool_counts = {}  # 同一ツール呼び出しの発生回数（3回目で無限ループ判定）
    error_signature_counts = {}  # 同一エラー文本の発生回数（2回目で自動修正を打ち切り）
    force_tool_synthesis = False  # 重複ツール停止時など、生ログを本文にせず合成へ回す
    files_written_this_run = False
    last_gate_meta: dict | None = None
    gate_fix_attempts = 0

    def _run_task_completion_gate() -> dict:
        nonlocal last_gate_meta
        meta = run_task_completion_gate(
            ws_dir,
            spec_internal=extract_spec_internal(executor_sys_prompt, instruction),
        )
        last_gate_meta = meta
        return meta

    executor_sys_prompt = ensure_executor_guards(
        executor_sys_prompt, has_search=bool(search_results)
    )

    while loop_count < max_tool_loops:
        loop_count += 1
        
        # モード別セーフティ・ループ上限：チャットでも指数クォート数本＋本文生成の余地を残す
        is_coding_task = any(tag in final_accumulated_response for tag in ["<file", "<replace", "<run_command"])
        chat_tool_cap = 8
        if mode not in ["coding", "task"] and loop_count > chat_tool_cap and not is_coding_task:
            logger.info(
                f"🛑 チャット・検索モードのツールループ上限({chat_tool_cap}回)に達したため完了します。"
            )
            if tool_handler.tool_results or search_results:
                force_tool_synthesis = True
            break
        
        if yield_sse_func:
            yield_sse_func({"type": "status", "status": "responding"})
        
        # --- Executor呼び出し ---
        if loop_count == 1:
            exec_user_input = user_input + "\n\n【動的システムコンテキスト】\n" + executor_dynamic_sys
            # 🔴 Claude Code準拠: 初回にプロジェクト全体コンテキストを自動注入
            if mode in ["task", "research", "coding"]:
                try:
                    from app.core.project_context import gather_project_context
                    proj_ctx = await gather_project_context(ws_dir)
                    if proj_ctx:
                        exec_user_input += "\n\n" + proj_ctx
                except Exception as e:
                    logger.warning(f"プロジェクトコンテキスト収集失敗: {e}")
            exec_history = history_messages
        else:
            exec_user_input = loop_history[-1]["content"]
            
            # 🔴 Claude Code準拠: 重要度に基づいた賢い圧縮
            compressed_loop = await _smart_compress_loop_history(
                loop_history, session_id=session_id
            )
            
            exec_history = (
                history_messages
                + [{"role": "user", "content": user_input + "\n\n【動的システムコンテキスト】\n" + executor_dynamic_sys}]
                + compressed_loop
            )
        
        stream_response = ""
        tool_tag_detected = False
        
        # --- Executorのストリーミングを読み取り ---
        stream = run_executor(
            user_input=exec_user_input,
            instruction=instruction,
            search_results=search_results,
            memory_text=memory_text,
            history_messages=exec_history,
            mode=mode,
            system_instruction=executor_sys_prompt,
        )
        
        buffer = ""
        in_xml_block = False

        async for chunk in iter_executor_stream(stream, yield_sse_func):
            buffer += chunk
            
            while '\n' in buffer and not tool_tag_detected:
                line, buffer = buffer.split('\n', 1)
                
                if not in_xml_block:
                    match = tool_tag_start_pattern.search(line)
                    if match:
                        in_xml_block = True
                        stream_response += line + '\n'
                        # 同じ行内で完結するセルフクロージングタグ or 閉じタグをチェック
                        if self_closing_pattern.search(line) or closing_tag_pattern.search(line):
                            in_xml_block = False
                            tool_tag_detected = True
                            break
                        continue
                
                if in_xml_block:
                    stream_response += line + '\n'
                    if self_closing_pattern.search(line) or closing_tag_pattern.search(line):
                        in_xml_block = False
                        tool_tag_detected = True
                        break
                else:
                    stream_response += line + '\n'
            
            if tool_tag_detected:
                break
        
        # ストリーム末尾で改行を伴わずにバッファに残ったタグやテキストを処理・救済
        if not tool_tag_detected and buffer.strip():
            line = buffer.strip()
            stream_response += line + '\n'
            if (
                tool_tag_start_pattern.search(line)
                or self_closing_pattern.search(line)
                or closing_tag_pattern.search(line)
                or in_xml_block
            ):
                tool_tag_detected = True
        elif buffer:
            stream_response += buffer + '\n'

        # --- ツール実行 ---
        if tool_tag_detected:
            try:
                current_response, tool_events = await tool_handler.execute_tools(stream_response)
            except Exception as e:
                logger.error(f"ToolHandler error: {e}")
                return stream_response, f"ツール実行エラー: {e}", escalation_history
            
            # エスカレーション検出
            if tool_handler.has_escalation:
                escalation_history.extend(tool_handler.escalation_history)
                logger.info(f"🔃 エスカレーション検出 ({len(escalation_history)}件)")
                
                if len(escalation_history) < max_supervisor_retries:
                    # Supervisorでエラー分析＋修正指示を生成
                    supervisor_result = await _analyze_with_supervisor(
                        escalation_history=escalation_history,
                        user_input=user_input,
                        instruction=instruction,
                        supervisor_sys_prompt=supervisor_sys_prompt,
                        supervisor_dynamic_sys=supervisor_dynamic_sys,
                        mode=mode,
                        history_messages=history_messages,
                        yield_sse_func=yield_sse_func,
                    )
                    
                    if supervisor_result:
                        new_instruction = supervisor_result
                        tool_results_msg = (
                            "【システムからの分析結果】\n"
                            f"前回の実行でエラーが発生したため、Supervisorが分析しました。\n"
                            f"修正指示: {new_instruction}\n"
                        )
                        loop_history.append({"role": "assistant", "content": stream_response})
                        loop_history.append({"role": "user", "content": tool_results_msg})
                        instruction = new_instruction  # 修正指示で上書き
                        _clear_ui_with_progress(yield_sse_func, _ui_progress("re_run_tests"))
                        final_accumulated_response = ""
                        continue  # 再実行
                else:
                    # 上限到達
                    final_accumulated_response += stream_response + "\n"
                    break
            
            # ツール結果のエラーチェック
            has_tool_results = bool(tool_handler.tool_results and any(r.strip() for r in tool_handler.tool_results))
            
            if has_tool_results:
                has_error = False
                error_abort = False
                for result in tool_handler.tool_results:
                    error_info = _detect_error(result)
                    if error_info:
                        has_error = True
                        logger.info(f"🔧 エラー検出、自動修正を試みます (loop {loop_count})")

                        # 同一エラーの反復検出: 同じエラー文本が2回出たら自動修正では解決不能と
                        # 判断し、空転（LLMコール浪費）を止めて回答合成パスへ引き渡す。
                        error_sig = _error_signature(error_info)
                        error_signature_counts[error_sig] = error_signature_counts.get(error_sig, 0) + 1
                        if error_signature_counts[error_sig] >= 2:
                            logger.warning(f"⛔ 同一エラーが2回反復したため自動修正を中止します: {error_sig[:100]}")
                            error_abort = True
                            break

                        if loop_count < max_supervisor_retries:
                            error_context = (
                                "【ツール実行エラー】\n"
                                f"{error_info}\n\n"
                                "上記エラーを分析し、修正したコードを再実行してください。\n"
                                "※外部MCPサーバーの正しい呼び出し形式: <mcp_call server=\"サーバー名\" tool=\"ツール名\" args='{\"key\":\"value\"}' />\n"
                                "（server= と tool= は分離し、tool= にサーバー名を含めない。args は必須。"
                                "Roblox_Studio のほぼ全ツールは args に \"datamodel_type\": \"Edit\" が必須。"
                                "サーバー一覧は list_servers、ツール一覧は list_tools で確認可能）"
                            )
                            loop_history.append({"role": "assistant", "content": stream_response})
                            loop_history.append({"role": "user", "content": error_context})
                            
                            supervisor_result = await _analyze_with_supervisor(
                                escalation_history=[error_info],
                                user_input=user_input,
                                instruction=instruction,
                                supervisor_sys_prompt=supervisor_sys_prompt,
                                supervisor_dynamic_sys=supervisor_dynamic_sys,
                                mode=mode,
                                history_messages=history_messages,
                                yield_sse_func=yield_sse_func,
                            )
                            if supervisor_result:
                                instruction = supervisor_result
                                _clear_ui_with_progress(yield_sse_func, _ui_progress("fix_and_retry"))
                                final_accumulated_response = ""
                                continue
                            else:
                                # Supervisor応答なし（JSONパース失敗等）→ 同じ指示で空転しないよう打ち切る
                                error_abort = True
                                break
                        else:
                            error_abort = True
                            break
                if error_abort:
                    # エラー自動修正の打ち切り: while ループ自体を終了する
                    # （従来は for しか抜けず、max_tool_loops まで空転してLLMコールを浪費していた）
                    logger.warning("🛑 エラー自動修正の上限に到達したためループを終了し、現在の結果で回答を合成します")
                    final_accumulated_response += stream_response + "\n"
                    force_tool_synthesis = True
                    break
                
                if not has_error:
                    # 完全タグでシグネチャ抽出（args内のLuau比較演算子 > 等で切断されないように）
                    tag_match = re.search(r'<(mcp_call|search|read_url)\b[\s\S]*?(?:/>|</\1>)', stream_response)
                    if not tag_match:
                        tag_match = re.search(r'<(mcp_call|search|read_url)[^>]*>', stream_response)
                    sig = tag_match.group(0) if tag_match else None
                    if sig:
                        executed_tool_counts[sig] = executed_tool_counts.get(sig, 0) + 1
                    # 3回目以降の同一呼び出しのみ無限ループと判定
                    # （エラー修正後の再試行や search_game_tree の再確認等、正当な2回目は許容）
                    if sig and executed_tool_counts[sig] >= 3:
                        logger.warning(f"🛑 同一ツール呼び出しの重複検出により無限ループをシャットダウンします ({executed_tool_counts[sig]}回目): {sig[:200]}")
                        # 生の tool_results をユーザー本文に連結しない。合成パスへ回す。
                        loop_history.append({"role": "assistant", "content": stream_response})
                        tool_msg = "【システムからのツール実行結果】\n" + "\n\n".join(tool_handler.tool_results)
                        loop_history.append({"role": "user", "content": tool_msg})
                        if tool_handler.tool_results:
                            dump = "\n\n".join(tool_handler.tool_results)
                            search_results = (
                                f"{search_results}\n\n{dump}".strip() if search_results else dump
                            )
                        final_accumulated_response = ""
                        force_tool_synthesis = True
                        break

                    loop_history.append({"role": "assistant", "content": stream_response})
                    tool_msg = "【システムからのツール実行結果】\n" + "\n\n".join(tool_handler.tool_results)
                    loop_history.append({"role": "user", "content": tool_msg})
                    last_good_user_visible = _remember_good(last_good_user_visible, stream_response)

                    from app.core.completion_status import wants_code_in_chat
                    wrote_file = bool(
                        re.search(
                            r"<(?:file|replace|edit)\b",
                            stream_response,
                            re.IGNORECASE,
                        )
                    )
                    if wrote_file:
                        files_written_this_run = True
                    if wrote_file and mode in ("task", "coding"):
                        # Completion gate: acceptance + build — reinject if not ok
                        try:
                            gate = _run_task_completion_gate()
                            if not gate.get("ok") and gate_fix_attempts < this_run_gate_cap:
                                gate_fix_attempts += 1
                                if yield_sse_func:
                                    yield_sse_func({
                                        "type": "status",
                                        "status": "incomplete",
                                        "detail": "completion_gate",
                                    })
                                loop_history.append({"role": "assistant", "content": stream_response})
                                loop_history.append({
                                    "role": "user",
                                    "content": _gate_reinject_message(gate),
                                })
                                _clear_ui_with_progress(
                                    yield_sse_func,
                                    "完了ゲート未達 → 未達項目を修正中…",
                                )
                                final_accumulated_response = ""
                                continue
                        except Exception as gate_err:
                            logger.warning(f"completion gate error: {gate_err}")

                    if wrote_file and mode in ("task", "coding", "research"):
                        if wants_code_in_chat(user_input):
                            loop_history.append({
                                "role": "user",
                                "content": (
                                    "【システム通知・最重要】ユーザーはコード本文をチャットで求めている。\n"
                                    "「ファイル作成完了」だけのメタ報告は禁止。\n"
                                    "1) 保存パスを1行\n"
                                    "2) 変更点の要点を短く\n"
                                    "3) 続けてコード全文を ```言語 フェンスでチャットに出力（省略禁止）\n"
                                    "長すぎて切れそうなら先に <file> 済みの内容をそのままフェンスで貼ること。\n"
                                    "可能なら <run_command>python -m py_compile 対象.py</run_command> で構文チェック。"
                                ),
                            })
                        else:
                            loop_history.append({
                                "role": "user",
                                "content": (
                                    "【システム通知】ファイル保存済み。次ターンではパスと要点を短く伝え、"
                                    "必要なら python -m py_compile で構文チェックしてください。"
                                    "「作成完了」だけの空疎な一文で終わらないこと。"
                                ),
                            })
                    _clear_ui_with_progress(
                        yield_sse_func,
                        "ファイル保存／ツール完了 → 回答を組み立て中…" if wrote_file else "ツール完了 → 回答を続けます…",
                    )
                    final_accumulated_response = ""
                    continue
            else:
                # ツールタグは検出したが結果が空 → 自動リトライ（最大2回）
                logger.warning(f"⚠️ ツール実行結果が空: {stream_response[:100]}...")
                loop_history.append({"role": "assistant", "content": stream_response})
                if empty_result_retry_count < 2 and loop_count < max_supervisor_retries:
                    empty_result_retry_count += 1
                    logger.info(f"🔄 空のツール結果を検出。リトライします ({empty_result_retry_count}/2)")
                    retry_msg = (
                        "【システム通知（自動リトライ）】\n"
                        "ツールタグを検出できましたが、実行結果が空でした（Docker未起動やタイムアウトの可能性）。\n"
                        "もし環境に依存するコマンドを実行していた場合は、一度コマンド実行を省き、<file> や <replace> によるファイル操作のみで作業を進めてください。"
                    )
                    loop_history.append({"role": "user", "content": retry_msg})
                    _clear_ui_with_progress(yield_sse_func, _ui_progress("empty_tool_retry"))
                    final_accumulated_response = ""
                    continue
                else:
                    no_result_msg = (
                        "【システム通知】\n"
                        "ツールタグを検出しましたが、実行結果が空でした。\n"
                        "コマンドが完了するまで少し待ってから、もう一度試してください。\n"
                        "エラーが続く場合は、環境設定（Docker、Flutter SDK等）を確認してください。"
                    )
                    loop_history.append({"role": "user", "content": no_result_msg})
                    final_accumulated_response += stream_response + "\n" + no_result_msg + "\n"
                    break  # 無限ループ防止のため一旦会話モードへ
        else:  # tool_tag_detected == False
            # --- 🔴 新規追加: Executor出力が完全空（0文字）の場合のリトライ ---
            if not stream_response.strip():
                logger.warning(f"⚠️ Executorからの出力が完全空（0文字）です (loop {loop_count})")
                if empty_output_retry_count < 1 and loop_count < max_supervisor_retries:
                    empty_output_retry_count += 1
                    logger.info("🔄 空出力を検出したため自動リトライします")
                    retry_msg = (
                        "【システム警告（自動差し戻し）】\n"
                        "直前の応答が空（0文字）でした。空の再生成を繰り返さず、"
                        "具体的なテキストかツールタグ（<file>, <read_file> 等）を必ず1つ以上出力してください。"
                    )
                    # 空 assistant を history に積まない（トークン浪費防止）
                    loop_history.append({"role": "user", "content": retry_msg})
                    _clear_ui_with_progress(yield_sse_func, _ui_progress("empty_regen"))
                    final_accumulated_response = ""
                    continue
                else:
                    err_msg = "*(⚠️ 応答の生成に失敗しました。もう一度お試しください)*"
                    final_accumulated_response += err_msg + "\n"
                    break

            # ツールタグなし → 通常の回答として返す
            from app.core.fact_filters.markup import normalize_final_answer_body

            logger.warning(
                f"🔍 [DEBUG] LLMの生出力(ツールなし): {repr(stream_response[:500])}"
                + ("…" if len(stream_response) > 500 else "")
            )
            body, empty_after_marker = normalize_final_answer_body(stream_response)
            if empty_after_marker:
                # <<<FINAL_ANSWER>>> with no prose → force synthesis; drop CoT preamble
                logger.warning(
                    "⚠️ FINAL_ANSWER marker with empty body — will synthesize from search/tools"
                )
                force_tool_synthesis = True
                loop_history.append({"role": "assistant", "content": stream_response})
                _clear_ui_with_progress(
                    yield_sse_func,
                    _ui_progress("compose_from_search"),
                )
                # Leave final_accumulated empty so need_synth runs
                break

            visible = body if body.strip() else stream_response
            final_accumulated_response += visible + "\n"
            last_good_user_visible = _remember_good(last_good_user_visible, stream_response)

            # 長文コードの chat 直書きを検知 → file 誘導（1回）
            # ユーザーが本文要求でも、途切れ防止のため一旦 file に落としてから読み戻す
            code_fences = len(re.findall(r"```", visible))
            long_code_dump = (
                mode in ("task", "coding", "research")
                and code_fences >= 2
                and len(visible) > 2500
                and not re.search(r"<file\b", stream_response, re.IGNORECASE)
                and loop_count < 2
            )
            if long_code_dump:
                logger.info("📝 長文コードのチャット直書きを検知 → <file> 誘導")
                loop_history.append({"role": "assistant", "content": stream_response})
                loop_history.append({
                    "role": "user",
                    "content": (
                        "【システム警告】長いコードがチャット直書きです（途切れ・トークン浪費の原因）。\n"
                        "今すぐ `<file path=\"...\">全文</file>` で保存し、次ターンで"
                        "パス＋要点＋コード全文フェンスを出力してください。メタ完了宣言のみは禁止。"
                    ),
                })
                _clear_ui_with_progress(yield_sse_func, _ui_progress("save_long_then_body"))
                continue

            # ハルシネーションチェック（ツール指示があるのにタグがない）
            tool_keywords = any(kw in instruction for kw in [
                '<read_url', '<search',
                'ファイルを作成', 'ファイルを修正', 'コードを修正', 'コードを書',
                'コマンドを実行',
            ])
            has_any_xml = bool(re.search(
                r'<(file|replace|run_command|read_url|read_file|list_dir|search|search_news|'
                r'search_codebase|grep_search|view_file|mcp_call|escalate)',
                stream_response
            ))
            
            if mode == "task" and tool_keywords and not has_any_xml and loop_count < 2:
                logger.warning(f"⚠️ ハルシネーション検出: ツール指示を無視 (loop {loop_count})")
                retry_msg = (
                    "【システム警告（自動差し戻し）】\n"
                    "テキストで「修正しました」と報告していますが、"
                    "実際のXMLタグ（<file>, <replace>, <run_command> 等）が出力されていません。\n"
                    "口頭でのロールプレイは禁止されています。\n"
                    "直ちに正しいXMLタグを出力してください。"
                )
                loop_history.append({"role": "assistant", "content": stream_response})
                loop_history.append({"role": "user", "content": retry_msg})
                continue
            
            break  # 通常の会話として終了
            
    hit_loop_cap = loop_count >= max_tool_loops
    if hit_loop_cap:
        logger.warning(f"⚠️ 最大ツール実行ループ数 ({max_tool_loops}) に到達したためループを終了しました。")
        final_accumulated_response += (
            f"\n\n*(⚠️ 最大実行ループ数 {max_tool_loops} に到達しました。"
            "作業は未完了の可能性があります。「続きを作成して」と指示してください)*"
        )
        if yield_sse_func:
            yield_sse_func({
                "type": "status",
                "status": "incomplete",
                "detail": f"max_tool_loops_{max_tool_loops}",
            })

    # Final completion gate for task/coding after file writes
    if files_written_this_run and mode in ("task", "coding"):
        try:
            gate = last_gate_meta or _run_task_completion_gate()
            final_accumulated_response = append_final_gate_banner(
                final_accumulated_response,
                gate,
                hit_loop_cap=hit_loop_cap,
                yield_sse_func=yield_sse_func,
            )
        except Exception as e:
            logger.warning(f"final completion gate: {e}")
            gate = last_gate_meta
        if persist_gate:
            try:
                persist_gate(
                    session_id,
                    gate or last_gate_meta,
                    hit_loop_cap=hit_loop_cap,
                    mode=mode,
                    user_input=user_input,
                    prev=prev_goal,
                )
            except Exception as e:
                logger.warning("goal persist skipped: %s", e)
    elif hit_loop_cap and mode in ("task", "coding"):
        if persist_gate:
            try:
                persist_gate(
                    session_id,
                    last_gate_meta or {"ok": False, "verdict": "fail", "acceptance": {}, "build": {}},
                    hit_loop_cap=True,
                    mode=mode,
                    user_input=user_input,
                    prev=prev_goal,
                )
            except Exception as e:
                logger.warning("goal persist (loop cap) skipped: %s", e)

    final_accumulated_response, tool_results_summary = await finalize_loop_response(
        user_input=user_input,
        instruction=instruction,
        executor_sys_prompt=executor_sys_prompt,
        mode=mode,
        search_results=search_results,
        memory_text=memory_text,
        exec_history=exec_history,
        loop_history=loop_history,
        tool_handler=tool_handler,
        final_accumulated_response=final_accumulated_response,
        force_tool_synthesis=force_tool_synthesis,
        last_good_user_visible=last_good_user_visible,
        continuation_attempted=continuation_attempted,
        yield_sse_func=yield_sse_func,
    )
    return final_accumulated_response, tool_results_summary, escalation_history
