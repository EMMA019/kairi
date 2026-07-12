"""
Autonomous Execution Loop — 自律実行ループ

【目的】
Executorがツールを実行した結果を自動解析し、エラー発生時は
Supervisorがログを分析して修正指示を生成→再実行するループ。

【従来の流れ vs 改善後】
- 従来: Executorツール実行 → 結果表示 → 次のユーザー入力を待つ
- 改善後: Executorツール実行 → エラー検出 → 自動修正 → 再実行 → 成功確認

【KVメモリルールの遵守】
- このループは「ユーザーの指示」の文脈内でのみ動作
- 過去の会話やKVメモリを勝手に参照することは一切しない
- 全てSupervisorの instruction に基づいて実行
"""
import json
import re
import asyncio
from typing import Optional
from app.core.supervisor import run_supervisor
from app.core.executor import run_executor
from app.core.tools.handler import ToolHandler
from app.utils.logger import get_logger
from app.routers.settings import app_settings

logger = get_logger(__name__)

# エラーパターン検出用の正規表現
ERROR_PATTERNS = [
    re.compile(r'(Error|Exception|Traceback|Failed|SyntaxError|ImportError|ModuleNotFoundError)', re.IGNORECASE),
    re.compile(r'(errno|exit code [1-9]|non-zero|returned 1)', re.IGNORECASE),
    re.compile(r'(not found|No such|does not exist|cannot find|unable to resolve)', re.IGNORECASE),
    re.compile(r'(permission denied|access denied|EACCES|EACCESS)', re.IGNORECASE),
    re.compile(r'(timeout|timed out|connection refused|connection reset)', re.IGNORECASE),
]

# 誤検出（偽陽性）を除外するためのパターン
IGNORE_ERROR_PATTERNS = [
    re.compile(r'(npm warn|npm notice|deprecation|deprecated|SKIPPING|skipped|nothing to commit|0 vulnerabilities|no such file or directory, open \'.*package-lock\.json\')', re.IGNORECASE),
    re.compile(r'(\b0 failed\b)', re.IGNORECASE),
]

# 成功パターン（明示的に成功を示す）
SUCCESS_PATTERNS = [
    re.compile(r'(success|completed|installed|created|updated|deleted)', re.IGNORECASE),
    re.compile(r'(\b[1-9]\d*\s+passed\b|100%|all good|build success)', re.IGNORECASE),
]


def _detect_test_failure(tool_result: str) -> Optional[dict]:
    """テスト結果を構造化して解析（pytest, jest, go test, npm test等対応）"""
    if not tool_result:
        return None
        
    # pytest / unittest
    if "passed" in tool_result.lower() or "failed" in tool_result.lower() or "error" in tool_result.lower():
        passed_m = re.search(r'(\d+)\s+passed', tool_result, re.IGNORECASE)
        failed_m = re.search(r'(\d+)\s+failed', tool_result, re.IGNORECASE)
        error_m = re.search(r'(\d+)\s+error', tool_result, re.IGNORECASE)
        
        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        errors = int(error_m.group(1)) if error_m else 0
        
        if passed > 0 or failed > 0 or errors > 0:
            success = (failed == 0 and errors == 0 and passed > 0)
            return {
                "framework": "pytest",
                "passed": passed,
                "failed": failed + errors,
                "success": success,
                "summary": f"Pytest: {passed} passed, {failed+errors} failed/error"
            }
            
    # Jest / Vitest
    m = re.search(r'Tests:\s*(?:(\d+)\s+failed,\s*)?(\d+)\s+passed', tool_result, re.IGNORECASE)
    if m:
        failed = int(m.group(1) or 0)
        passed = int(m.group(2))
        return {"framework": "jest", "passed": passed, "failed": failed, "success": failed == 0, "summary": f"Jest: {passed} passed, {failed} failed"}
        
    # Go test
    if "--- FAIL:" in tool_result or "FAIL\t" in tool_result:
        return {"framework": "gotest", "passed": 0, "failed": 1, "success": False, "summary": "Go test: FAIL detected"}
    if "--- PASS:" in tool_result or "ok\t" in tool_result:
        return {"framework": "gotest", "passed": 1, "failed": 0, "success": True, "summary": "Go test: PASS detected"}
        
    return None


def _detect_error(tool_result: str) -> Optional[str]:
    """ツール実行結果からエラーを検出"""
    if not tool_result or len(tool_result.strip()) < 5:
        return None
        
    # テスト失敗の専用チェック
    test_info = _detect_test_failure(tool_result)
    if test_info and not test_info["success"]:
        return f"【テスト失敗】{test_info['summary']}\n" + tool_result[-1500:]
    
    # 除外パターンのチェック（警告や正常な情報メッセージなど）
    # 全体が除外パターンだけにマッチする場合はエラーとしない
    lines = tool_result.split('\n')
    error_lines = []
    
    for i, line in enumerate(lines):
        # 除外パターンが含まれている行はエラー判定をスキップ
        if any(ignore_p.search(line) for ignore_p in IGNORE_ERROR_PATTERNS):
            continue
        for pattern in ERROR_PATTERNS:
            if pattern.search(line):
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                error_lines.extend(lines[start:end])
                error_lines.append('---')
                break
                
    if error_lines:
        context = '\n'.join(error_lines[-50:])  # 最大50行
        return context
    
    return None


def _detect_success(tool_result: str) -> bool:
    """ツール実行結果が成功を示しているかチェック"""
    if not tool_result:
        return False
        
    test_info = _detect_test_failure(tool_result)
    if test_info:
        return test_info["success"]
    
    # 明らかなエラーがある場合は成功とみなさない
    if _detect_error(tool_result):
        if 'warning' in tool_result.lower() and not any(k in tool_result.lower() for k in ['error', 'failed', 'exception']):
            pass
        else:
            return False
    
    # 成功パターンをチェック
    for pattern in SUCCESS_PATTERNS:
        if pattern.search(tool_result):
            return True
    
    return True  # エラーがなければ一応成功扱い


async def _smart_compress_loop_history(loop_history: list[dict], max_total_chars: int = 30000) -> list[dict]:
    """ツール結果の重要度に基づいた賢い圧縮（Claude Code準拠）"""
    if len(loop_history) <= 6:
        return loop_history[:-1]  # 最新3ターン以内ならそのまま返す（最後の要素は別途処理されるため除外）
        
    recent = loop_history[-6:-1]  # 直近3ターン（最新の入力除く）は完全保持
    older = loop_history[:-6]
    
    compressed = []
    for msg in older:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        
        if role == "assistant":
            # 生成コードは模倣防止のため保持
            compressed.append(msg)
        else:
            # ツール結果の重要度判定
            has_error = _detect_error(content) is not None or "【テスト失敗】" in content or "エラー" in content
            is_file_read = "ファイル読み込み成功" in content or "📄" in content
            
            if has_error:
                # エラーメッセージは圧縮しない（原因追究の文脈を失わないため）
                compressed.append(msg)
            elif is_file_read and len(content) <= 3000:
                # ファイル内容も3000文字以内なら保持
                compressed.append(msg)
            elif len(content) > 500:
                # それ以外のディレクトリ一覧や長すぎる実行結果は要約
                compressed.append({
                    "role": role,
                    "content": content[:200] + f"\n...[ツール結果 ({len(content)}文字) キャッシュ効率・重要度判定により圧縮]...\n" + content[-200:]
                })
            else:
                compressed.append(msg)
                
    return compressed + recent

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
            async for c in original_stream:
                if in_tag:
                    tag_buf += c
                    if ">" in tag_buf or "\n" in tag_buf:
                        if not re.search(r'<(search|read_url|read_file|run_command|file|replace|list_dir|get_hot_stocks|search_news|mcp_call|escalate)', tag_buf):
                            if yield_sse_func:
                                yield_sse_func({"type": "chunk", "content": tag_buf})
                        tag_buf = ""
                        in_tag = False
                else:
                    if "<" in c:
                        in_tag = True
                        tag_buf += c
                    else:
                        if yield_sse_func:
                            yield_sse_func({"type": "chunk", "content": c})
                yield c
            if tag_buf and not in_tag:
                if yield_sse_func:
                    yield_sse_func({"type": "chunk", "content": tag_buf})
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
            final_accumulated_response += stream_response + "\n"
            
            # ハルシネーションチェック（ツール指示があるのにタグがない）
            tool_keywords = any(kw in instruction for kw in [
                '<file', '<replace', '<run_command', '<read_file', '<list_dir',
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
            strip_out_of_period_event_mentions,
            verify_holiday_and_weekend_claims,
            strip_excuse_hallucinations,
        )
        _, final_accumulated_response = check_currency_consistency(final_accumulated_response)
        _, final_accumulated_response = verify_numbers_exist_in_source(final_accumulated_response, str(search_results or ""))
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

    final_accumulated_response = re.sub(r'<think>.*?</think>', '', final_accumulated_response, flags=re.DOTALL)
    final_accumulated_response = re.sub(r'(?m)^(?:まず、ユーザーの発言を分析します[^\n]*\n+|Output format:[^\n]*\n+|user_intent_analysis:[^\n]*\n+)+', '', final_accumulated_response)
    final_accumulated_response = re.sub(r'【一般検索結果:.*?】\s*(?:\[brave\s*\[Tier.*?\]\].*?\n?)+', '', final_accumulated_response, flags=re.DOTALL)

    return final_accumulated_response.strip(), tool_results_summary, escalation_history


async def _analyze_with_supervisor(
    escalation_history: list,
    user_input: str,
    instruction: str,
    supervisor_sys_prompt: str,
    supervisor_dynamic_sys: str,
    mode: str,
    history_messages: list,
    yield_sse_func=None,
) -> Optional[str]:
    """
    Supervisorにエラー分析＋修正指示を依頼。
    
    Returns:
        新しい instruction（文字列）、または None（分析失敗）
    """
    try:
        if yield_sse_func:
            yield_sse_func({"type": "status", "status": "thinking"})
        
        escalation_context = "\n".join([
            f"【エラー #{i+1}】\n{e}"
            for i, e in enumerate(escalation_history[-3:])  # 最新3件のみ
        ])
        
        analysis_prompt = (
            f"【前回のツール実行でエラーが発生しました】\n"
            f"{escalation_context}\n\n"
            f"【元の指示】\n{instruction}\n\n"
            f"上記エラーを分析し、修正したコードやコマンドを、"
            f"再度 Executor が実行できる形で instruction.facts_to_present に指示してください。"
            f"絶対に推測で原因をでっち上げず、エラーメッセージに基づいて正確に分析してください。"
        )
        
        supervisor_json, reasoning = await run_supervisor(
            user_input=user_input + "\n\n" + analysis_prompt + "\n\n" + supervisor_dynamic_sys,
            search_results=None,
            memory_text=None,
            history_messages=history_messages,
            mode=mode,
            system_instruction=supervisor_sys_prompt,
        )
        
        if yield_sse_func and reasoning:
            yield_sse_func({"type": "reasoning", "content": reasoning})
        
        instruction_dict = supervisor_json.get("instruction", {})
        if isinstance(instruction_dict, dict):
            facts = instruction_dict.get("facts_to_present", [])
            order = instruction_dict.get("logical_order", [])
            new_instruction = ""
            if facts:
                new_instruction += "【必ず含めるべき事実】\n"
                for f in facts:
                    new_instruction += f"- {f}\n"
            if order:
                new_instruction += "\n【回答の構成（順序）】\n"
                for o in order:
                    new_instruction += f"- {o}\n"
            return new_instruction if new_instruction.strip() else None
        
        return None
        
    except Exception as e:
        logger.error(f"Supervisor analysis error: {e}")
        return None