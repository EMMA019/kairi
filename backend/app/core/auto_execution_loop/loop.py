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
    escalation_history = []
    empty_result_retry_count = 0
    empty_output_retry_count = 0
    
    tool_handler = ToolHandler(
        session_id=session_id,
        mode=mode,
        allow_mocks="モック" in user_input or "ダミー" in user_input or "仮実装" in user_input,
    )
    
    # ワークスペースパスの解決
    try:
        from app.routers.workspace import get_workspace_dir
        ws_dir = str(get_workspace_dir())
    except Exception:
        from pathlib import Path
        ws_dir = str(Path(__file__).parent.parent.parent / "workspace")
    
    executed_tool_signatures = set()
    
    boundary_instruction = (
        "\n\n【構造的モダリティ分離（出力境界トークン）の厳守ルール】\n"
        "思考ログ・内部分析・途中メモとユーザーへの最終出力本文がバッファ上で混在するのを完全に防ぐため、"
        "ユーザーへの最終的な回答本文を開始する直前に必ず `<<<FINAL_ANSWER>>>` という区切りトークンを出力し、"
        "その後にのみ最終回答テキストを出力してください。\n"
        "※ツール呼び出し（<search>, <file> 等）のみを行うターンでは `<<<FINAL_ANSWER>>>` は不要です。"
    )
    universal_closed_world_instruction = (
        "\n\n【全ドメイン適用：動的・時系列クエリにおける完全閉世界（Closed-World）原則とパラメトリック記憶の遮断】\n"
        "現在は2026年です。政治、経済・金融（FRB/中央銀行/指標等）、企業人事（CEO/役員等）、スポーツ（選手/所属/監督）、"
        "エンタメ、テクノロジー等の時系列動向・最新ファクトに関する質問に対しては、事前学習データ（パラメトリック記憶）にある"
        "過去の固有名詞や人名（例：FRBパウエル議長等）を絶対にそのまま出力せず、必ず直近の検索結果（ソーステキスト）に明示的に"
        "記載されている最新の人名・固有エンティティのみを正確に拾って回答すること。\n"
        "ソーステキストに個人名の記載がなく役職名・肩書のみ（『FRB議長』『同社CEO』『現職監督』等）記載されている場合は、"
        "勝手に過去の記憶から個人名を推測・補完・上書きせず、ソース通りに『FRB議長』『同社CEO』のように役職名・一般名詞のみで記述してください。"
    )
    if "完全閉世界（Closed-World）原則" not in executor_sys_prompt:
        executor_sys_prompt += universal_closed_world_instruction

    if "<<<FINAL_ANSWER>>>" not in executor_sys_prompt:
        executor_sys_prompt += boundary_instruction
    
    while loop_count < max_tool_loops:
        loop_count += 1
        
        # モード別セーフティ・ループ上限：通常のチャット・お出かけ検索で無限ループを防ぐ
        is_coding_task = any(tag in final_accumulated_response for tag in ["<file", "<replace", "<run_command"])
        if mode not in ["coding", "task"] and loop_count > 3 and not is_coding_task:
            logger.info(f"🛑 チャット・検索モードのツールループ上限(3回)に達したため完了します。")
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
            compressed_loop = await _smart_compress_loop_history(loop_history)
            
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
        tool_tag_start_pattern = re.compile(
            r'<(file|replace|run_command|read_url|read_file|list_dir|search|search_news|'
            r'mcp_call|escalate)(?:\s|>|/>)'
        )
        self_closing_pattern = re.compile(
            r'<(file|replace|run_command|read_url|read_file|list_dir|search|search_news|'
            r'mcp_call|escalate)[^>]*/>',
            re.DOTALL
        )
        closing_tag_pattern = re.compile(
            r'</(file|replace|run_command|read_url|read_file|list_dir|search|search_news|'
            r'mcp_call|escalate)>',
            re.DOTALL
        )
        
        async def stream_with_newline(original_stream):
            tag_buf = ""
            in_tag = False
            in_think_block = False  # <think>ブロック内かどうか
            async for c in original_stream:
                if in_tag:
                    tag_buf += c
                    if ">" in tag_buf or "\n" in tag_buf:
                        match_think = re.search(r'<think\s*>', tag_buf)
                        match_end_think = re.search(r'</think\s*>', tag_buf)
                        
                        # <think> 開始タグ検出
                        if match_think:
                            in_think_block = True
                            # <think> より前のテキストがあれば出力
                            before_think = tag_buf[:match_think.start()]
                            if before_think and not in_think_block:
                                if yield_sse_func:
                                    yield_sse_func({"type": "chunk", "content": before_think})
                                yield before_think
                            
                            remainder = tag_buf[match_think.end():]
                            tag_buf = remainder
                            in_tag = "<" in tag_buf
                            continue
                            
                        # </think> 閉じタグ検出
                        elif match_end_think:
                            in_think_block = False
                            remainder = tag_buf[match_end_think.end():]
                            tag_buf = remainder
                            in_tag = "<" in tag_buf
                            if remainder and not in_tag:
                                if yield_sse_func:
                                    yield_sse_func({"type": "chunk", "content": remainder})
                                yield remainder
                            continue
                            
                        elif not re.search(r'<(search|read_url|read_file|run_command|file|replace|list_dir|search_news|mcp_call|escalate)', tag_buf):
                            if not in_think_block:
                                if yield_sse_func:
                                    yield_sse_func({"type": "chunk", "content": tag_buf})
                                yield tag_buf
                            tag_buf = ""
                            in_tag = False
                            continue
                        else:
                            # ツールタグを検出（SSEには流さず内部バッファへ）
                            # もしツールタグの前にテキストがあればそれは流す
                            tool_match = re.search(r'<(search|read_url|read_file|run_command|file|replace|list_dir|search_news|mcp_call|escalate)', tag_buf)
                            if tool_match and tool_match.start() > 0:
                                before_tool = tag_buf[:tool_match.start()]
                                if not in_think_block:
                                    if yield_sse_func:
                                        yield_sse_func({"type": "chunk", "content": before_tool})
                                    # yield before_tool  # yield it along with tag_buf below
                            
                            if not in_think_block:
                                yield tag_buf
                            tag_buf = ""
                            in_tag = False
                            continue
                else:
                    if "<" in c:
                        idx = c.find("<")
                        before_lt = c[:idx]
                        if before_lt and not in_think_block:
                            if yield_sse_func:
                                yield_sse_func({"type": "chunk", "content": before_lt})
                            yield before_lt
                        in_tag = True
                        tag_buf += c[idx:]
                        continue
                    else:
                        if not in_think_block:
                            if yield_sse_func:
                                yield_sse_func({"type": "chunk", "content": c})
                            yield c
                        continue
                        
            if tag_buf and not in_tag:
                if not in_think_block:
                    if yield_sse_func:
                        yield_sse_func({"type": "chunk", "content": tag_buf})
                    yield tag_buf
            elif tag_buf and in_tag:
                if not in_think_block:
                    # ストリーム終了時、タグが未完了なら流す
                    if yield_sse_func:
                        yield_sse_func({"type": "chunk", "content": tag_buf})
                    yield tag_buf
            yield '\n'
        
        async for chunk in stream_with_newline(stream):
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
                        if yield_sse_func:
                            yield_sse_func({"type": "clear_buffer"})
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
                for result in tool_handler.tool_results:
                    error_info = _detect_error(result)
                    if error_info:
                        has_error = True
                        logger.info(f"🔧 エラー検出、自動修正を試みます (loop {loop_count})")
                        
                        if loop_count < max_supervisor_retries:
                            error_context = (
                                "【ツール実行エラー】\n"
                                f"{error_info}\n\n"
                                "上記エラーを分析し、修正したコードを再実行してください。"
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
                                if yield_sse_func:
                                    yield_sse_func({"type": "clear_buffer"})
                                final_accumulated_response = ""
                                continue
                        else:
                            final_accumulated_response += stream_response + "\n"
                            break
                
                if not has_error:
                    tag_match = re.search(r'<(mcp_call|search|read_url)[^>]*>', stream_response)
                    sig = tag_match.group(0) if tag_match else None
                    if sig and sig in executed_tool_signatures:
                        logger.warning(f"🛑 同一ツール呼び出しの重複検出により無限ループをシャットダウンします: {sig}")
                        final_accumulated_response += stream_response + "\n\n" + "\n\n".join(tool_handler.tool_results)
                        break
                    if sig:
                        executed_tool_signatures.add(sig)

                    loop_history.append({"role": "assistant", "content": stream_response})
                    tool_msg = "【システムからのツール実行結果】\n" + "\n\n".join(tool_handler.tool_results)
                    loop_history.append({"role": "user", "content": tool_msg})
                    if yield_sse_func:
                        yield_sse_func({"type": "clear_buffer"})
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
                    if yield_sse_func:
                        yield_sse_func({"type": "clear_buffer"})
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
                        "直前の応答が空（0文字）でした。指示やタスク内容を確認し、具体的なテキストやツールタグ（<file>, <read_file> 等）を出力して作業を進めてください。"
                    )
                    loop_history.append({"role": "assistant", "content": ""})
                    loop_history.append({"role": "user", "content": retry_msg})
                    if yield_sse_func:
                        yield_sse_func({"type": "clear_buffer"})
                    final_accumulated_response = ""
                    continue
                else:
                    err_msg = "*(⚠️ 応答の生成に失敗しました。もう一度お試しください)*"
                    final_accumulated_response += err_msg + "\n"
                    break

            # ツールタグなし → 通常の回答として返す
            logger.warning(f"🔍 [DEBUG] LLMの生出力(ツールなし): {repr(stream_response)}")
            final_accumulated_response += stream_response + "\n"
            
            # ハルシネーションチェック（ツール指示があるのにタグがない）
            tool_keywords = any(kw in instruction for kw in [
                '<read_url', '<search',
                'ファイルを作成', 'ファイルを修正', 'コードを修正', 'コードを書',
                'コマンドを実行',
            ])
            has_any_xml = bool(re.search(
                r'<(file|replace|run_command|read_url|read_file|list_dir|search|escalate)',
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
            
    if loop_count >= max_tool_loops:
        logger.warning(f"⚠️ 最大ツール実行ループ数 ({max_tool_loops}) に到達したためループを終了しました。")
        final_accumulated_response += f"\n\n*(⚠️ 最大実行ループ数 {max_tool_loops} に到達しました。作業が途中となっている場合は、「続きを作成して」と指示してください)*"
    
    try:
        from app.core.fact_filter import (
            check_currency_consistency,
            verify_numbers_exist_in_source,
            correct_common_typos,
            strip_unrequested_memory_mentions,
            strip_unrequested_yahoo_finance,
            strip_outdated_past_event_predictions,
            deduplicate_spot_listings,
            verify_exit_and_address_entanglement,
            sanitize_internal_tool_mentions,
            clean_broken_markdown_tables,
            verify_holiday_and_weekend_claims,
            strip_excuse_hallucinations,
            enforce_variable_numerical_claims,
            verify_temporal_leadership_claims,
            verify_chronological_rationalization,
            filter_unknown_entity_listings,
            sanitize_buffer_contamination,
            strip_out_of_period_event_mentions,
        )
        _, final_accumulated_response = check_currency_consistency(final_accumulated_response)
        _, final_accumulated_response = verify_numbers_exist_in_source(final_accumulated_response, str(search_results or ""))
        final_accumulated_response = verify_temporal_leadership_claims(final_accumulated_response, str(search_results or ""))
        final_accumulated_response = verify_chronological_rationalization(final_accumulated_response, str(search_results or ""))
        final_accumulated_response = filter_unknown_entity_listings(final_accumulated_response)
        final_accumulated_response = enforce_variable_numerical_claims(final_accumulated_response, str(search_results or ""))
        final_accumulated_response = correct_common_typos(final_accumulated_response)
        final_accumulated_response = strip_unrequested_memory_mentions(final_accumulated_response, user_input=user_input)
        final_accumulated_response = strip_unrequested_yahoo_finance(final_accumulated_response, user_input=user_input)
        final_accumulated_response = strip_outdated_past_event_predictions(final_accumulated_response)
        final_accumulated_response = deduplicate_spot_listings(final_accumulated_response)
        final_accumulated_response = verify_exit_and_address_entanglement(final_accumulated_response)
        final_accumulated_response = sanitize_internal_tool_mentions(final_accumulated_response)
        final_accumulated_response = clean_broken_markdown_tables(final_accumulated_response)
        final_accumulated_response = strip_out_of_period_event_mentions(final_accumulated_response)
        final_accumulated_response = verify_holiday_and_weekend_claims(final_accumulated_response)
        final_accumulated_response = strip_excuse_hallucinations(final_accumulated_response)
        final_accumulated_response = sanitize_buffer_contamination(final_accumulated_response)
    except Exception as e:
        logger.warning(f"Fact filter validation warning in auto_execution_loop: {e}")

    tool_results_summary = "\n".join(tool_handler.tool_results) if tool_handler.tool_results else ""

    if not final_accumulated_response.strip() and tool_results_summary:
        logger.info("⚠️ ツール実行後に最終回答が未生成だったため、ツール結果をもとに集約回答を生成します")
        try:
            final_prompt_msg = "検索結果・ツール実行結果を踏まえて、ユーザーの質問に対する最終回答を自然な文章で作成してください。XMLタグや生ログ（【一般検索結果: ...】など）はそのまま出力せず、整理して回答してください。"
            s_stream = run_executor(
                user_input=final_prompt_msg,
                instruction=instruction,
                search_results=search_results or tool_results_summary,
                memory_text=memory_text,
                history_messages=exec_history,
                mode=mode,
                system_instruction=executor_sys_prompt + "\n\n【重要】XMLタグやツールタグは一切出力しないでください。結果を踏まえた最終的な回答のみを自然な対話で出力すること。",
            )
            final_accumulated_response = ""
            async for chunk in s_stream:
                final_accumulated_response += chunk
                if yield_sse_func:
                    yield_sse_func({"type": "chunk", "content": chunk})
        except Exception as e:
            logger.error(f"Final synthesis error: {e}")

    if not final_accumulated_response.strip():
        logger.warning("⚠️ final_accumulated_response が空のため、ここまでのアシスタント応答から最終回答を復帰します")
        last_assist = ""
        for msg in reversed(loop_history):
            if msg.get("role") == "assistant" and msg.get("content"):
                clean_content = re.sub(r'<[^>]+>.*?</[^>]+>|<[^>]+/>', '', msg["content"], flags=re.DOTALL).strip()
                if clean_content:
                    last_assist = clean_content
                    break
        final_accumulated_response = last_assist

    if not final_accumulated_response.strip():
        if tool_results_summary:
            final_accumulated_response = "ツールを実行し、結果をシステムに連携しました。"
        else:
            final_accumulated_response = "*(⚠️ 応答が生成されなかったか、システムによってフィルタリングされました。もう一度お試しください)*"
            logger.warning("⚠️ 最終応答が空になったため、フォールバックメッセージを挿入しました。")

    # --- 物理分離構造パース: <<<FINAL_ANSWER>>> 以降を厳格抽出 ---
    if "<<<FINAL_ANSWER>>>" in final_accumulated_response:
        parts = final_accumulated_response.split("<<<FINAL_ANSWER>>>")
        final_accumulated_response = parts[-1].strip()

    final_accumulated_response = re.sub(r'<think>.*?</think>', '', final_accumulated_response, flags=re.DOTALL)
    # 閉じタグなしの <think> も除去（モデルが </think> を出力し忘れた場合）
    final_accumulated_response = re.sub(r'<think>(?:(?!</think>).)*$', '', final_accumulated_response, flags=re.DOTALL)
    final_accumulated_response = re.sub(r'(?m)^(?:まず、ユーザーの発言を分析します[^\n]*\n+|Output format:[^\n]*\n+|user_intent_analysis:[^\n]*\n+)+', '', final_accumulated_response)
    final_accumulated_response = re.sub(r'【一般検索結果:.*?】\s*(?:\[brave\s*\[Tier.*?\]\].*?\n?)+', '', final_accumulated_response, flags=re.DOTALL)
    try:
        from app.core.fact_filter import filter_unknown_entity_listings, sanitize_buffer_contamination
        final_accumulated_response = filter_unknown_entity_listings(final_accumulated_response)
        final_accumulated_response = sanitize_buffer_contamination(final_accumulated_response)
    except Exception as e:
        logger.warning(f"Final cleanup warning: {e}")

    return final_accumulated_response.strip(), tool_results_summary, escalation_history


