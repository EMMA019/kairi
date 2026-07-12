"""
チャット API ルーター — SSE ストリーミング対応（仕様書 §1-3 準拠）。

処理フロー:
1. リクエスト受信 → プロンプト構築
2. LLM に送信（非ストリーミングで全文取得）
3. <thinking> をパース → require_search 判定
4. 検索必要時: バッファ破棄 → 検索 → 再生成
5. <response> の内容を SSE で逐次送信
6. 完了後、会話履歴を SQLite に保存 + KV 書き込み
"""
import json
import asyncio
import re
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.chat import ChatRequest
from app.core.llm_client import call_model
from app.core.prompt_builder import build_system_instruction, build_search_retry_instruction
from app.core.kv_store import kv_store
from app.core.memory import extract_and_save_memory
from app.core.search import web_search
from app.core.database import get_db
from app.core.mood import get_mood
from app.utils.parser import parse_response
from app.utils.logger import get_logger
from app.routers.settings import app_settings
from app.core.cache_manager import get_search_cache, set_search_cache, check_greeting_short_circuit, get_llm_cache, set_llm_cache
from app.core.context_compressor import compress_messages_stage2
from app.core.gyaru import to_hyper_gal_v3

logger = get_logger(__name__)

router = APIRouter()

# セッションごとのフォローアップ履歴（インメモリ、サーバー再起動でリセット）
# メモリリーク防止: 最大200セッション分のみ保持
_MAX_FOLLOWUP_SESSIONS = 200
_followup_histories: dict[str, list[bool]] = {}


def _clip_search_results(text: str, max_bytes: int = 100_000) -> str:
    """検索結果を最大サイズにクリップ（57MB爆発防止）。全3箇所の代入で共通利用"""
    if not text or len(text) <= max_bytes:
        return text
    logger.warning(f"⚠️ 検索結果が大きすぎます ({len(text):,} bytes) → {max_bytes:,} bytesにクリップ")
    half = max_bytes // 2
    return text[:half] + f"\n\n[...検索結果が長すぎるため途中でカット ({len(text) - max_bytes} bytes削減)...]\n\n" + text[-half:]


def _extract_smart_snippet(text: str, max_chars: int = 15000) -> str:
    """論文や長文記事の冒頭（背景/アブスト）と後半（実験結果/Defense/結論）を両方保持するスマート抽出（トークン爆発防止仕様）"""
    if not text or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 5  # 前半約6,000文字（アブスト・序論）
    tail = max_chars * 3 // 5  # 後半約9,000文字（実験結果・Defense Mechanism・結論）
    return text[:head] + "\n\n[...中間セクション省略（トークン節約）...]\n\n" + text[-tail:]



def _sse_event(data: dict) -> str:
    """SSE イベントをフォーマット"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest):
    """メッセージ送信 → SSE ストリーミング応答"""
    session_id = request.session_id
    user_input = request.message
    mode = request.mode

    # フォローアップ・クールダウン判定（demo.py のロジック移植）
    # メモリリーク防止: 古いセッションを自動削除
    if len(_followup_histories) >= _MAX_FOLLOWUP_SESSIONS and session_id not in _followup_histories:
        oldest_key = next(iter(_followup_histories))
        del _followup_histories[oldest_key]
    history = _followup_histories.setdefault(session_id, [])
    followup_cooldown = len(history) >= 2 and all(history[-2:])

    # KV フィルタリング + KV一覧 + プロンプト構築
    relevant_kv = kv_store.filter_by_scope(user_input)
    filtered_kv_text = kv_store.format_for_prompt(relevant_kv)
    kv_summary = kv_store.format_summary()
    mood = get_mood()

    # --- ギャルモード (Lv3 Hyper Gal / omous Engine) 判定 ---
    settings_dict = app_settings.get()
    is_hyper_gal = (
        settings_dict.get("persona_style") in ["hyper_gal", "gal", "gyaru"]
        or ("ギャル" in user_input and "解除" not in user_input)
        or "lv3_gal" in user_input.lower()
    )

    # DB から会話履歴を取得
    messages = await _get_conversation_messages(session_id)

    async def event_stream():
        nonlocal mode, filtered_kv_text, kv_summary, user_input
        final_accumulated_response = ""
        from app.core.search_planner import plan_search
        from app.core.supervisor import run_supervisor
        from app.core.executor import run_executor
        
        # --- 🔴 Greeting Short-Circuit ---
        greeting_json = check_greeting_short_circuit(user_input)
        if greeting_json and mode == "chat" and not request.force_search:
            # 定型挨拶の場合はSupervisorをスキップ
            yield _sse_event({"type": "mode_switch", "mode": "chat"})
            
            # 簡単な返答を生成
            facts = greeting_json.get("instruction", {}).get("facts_to_present", [])
            order = greeting_json.get("instruction", {}).get("logical_order", [])
            
            # Executorで挨拶文を生成（簡易プロンプト）
            settings_dict = app_settings.get()
            persona_style = settings_dict.get("persona_style", "standard")
            if persona_style in ["hyper_gal", "gal", "gyaru"]:
                greeting_sys = """あなたは最強の平成ギャル相棒Kairiです。テンションMAXなギャル言葉・顔文字・絵文字を使って親密に挨拶を返してください。"""
            elif persona_style == "kairi_kansai":
                greeting_sys = """あなたは頼れる相棒Kairiです。親しみやすい関西弁で挨拶を返してください。"""
            else:
                greeting_sys = """あなたはユーザーと直接対話するAIです。簡潔で自然な挨拶を返してください。"""
            greeting_instruction = ""
            if facts:
                greeting_instruction += "【必ず含めるべき事実】\n"
                for f in facts:
                    greeting_instruction += f"- {f}\n"
            if order:
                greeting_instruction += "\n【回答の構成（順序）】\n"
                for o in order:
                    greeting_instruction += f"- {o}\n"
            
            stream = run_executor(
                user_input=user_input,
                instruction=greeting_instruction,
                search_results=None,
                memory_text=filtered_kv_text if greeting_json.get("memory_inject") else None,
                history_messages=messages,
                mode="chat",
                system_instruction=greeting_sys,
            )
            
            response_text = ""
            async for chunk in stream:
                if not is_hyper_gal:
                    yield _sse_event({"type": "chunk", "content": chunk})
                response_text += chunk
            
            if is_hyper_gal and response_text:
                response_text = to_hyper_gal_v3(response_text)
            
            await _save_messages(
                session_id, user_input, response_text,
                json.dumps(greeting_json, ensure_ascii=False),
                greeting_json, None, []
            )
            yield _sse_event({"type": "done", "content": response_text})
            return
        
        # --- 🔴 P0: Plan承認検出（前回のプランを「はい」で承認→即実装） ---
        if mode in ["chat", "task"]:
            try:
                kv_items = kv_store.filter_by_scope("pending_plan")
                approval_keywords = ["はい", "OK", "ok", "進めて", "お願い", "やろう", "GO", "go", "yes", "Yes", "うん", "いいよ", "頼む", "承認", "実装", "開始", "作って", "作成", "よろしく", "いいです", "大丈夫", "お願いします"]
                for item in kv_items:
                    summary = item.get("summary", {})
                    if summary.get("target") == "pending_plan" and any(kw in user_input for kw in approval_keywords):
                        logger.info("✅ Plan承認検出: 実装モードに移行")
                        mode = "task"
                        # plan内容をユーザー入力に追加
                        plan_note = summary.get("note", "")
                        if plan_note:
                            user_input = f"{user_input}\n\n【承認済みプラン】\n{plan_note}\n上記プランを直ちに実行せよ。"
                        # pending_planをクリア
                        try:
                            kv_store.delete(item["id"])
                        except Exception:
                            pass
                        break
            except Exception:
                pass
        
        # --- 🔴 P0: ユーザー発言内に直接URLが含まれる場合の自動ディープスクレイピング ---
        url_matches = re.findall(r'https?://[^\s)\]"]+', user_input)
        direct_url_texts = []
        if url_matches:
            from app.core.search.router import fetch_url
            for u in url_matches[:2]:
                yield _sse_event({"type": "status", "status": "scraping_url", "url": u})
                try:
                    content = await fetch_url(u)
                    if content and len(content.strip()) > 50:
                        snippet_content = _extract_smart_snippet(content, 15000)
                        direct_url_texts.append(f"【ユーザー指定URLの直接スクレイピング本文: {u}】\n{snippet_content}")
                        logger.info(f"直接URLフェッチ成功: {u} ({len(snippet_content)} bytes)")
                except Exception as e:
                    logger.warning(f"指定URL事前フェッチ失敗 {u}: {e}")

        # 1. 検索判定 (Search Planner LLM)
        yield _sse_event({"type": "status", "status": "planning_search"})
        
        search_plan = await plan_search(user_input, messages)
        search_needed = search_plan["needs_search"] or request.force_search
        search_queries = search_plan.get("search_queries", [])
        search_providers = search_plan.get("providers", ["brave"])
        if not search_queries:
            search_queries = [user_input]
        
        # --- 🔴 P0: 全検索領域における両面バランス検索セーフティネット（一方向・悲観・批判バイアスの防止） ---
        market_keywords = ["暴落", "下落", "懸念", "株", "相場", "半導体", "インテル", "AVGO", "ブロードコム", "急落", "調整", "バブル", "SOX"]
        negative_keywords = ["失敗", "問題", "危険", "批判", "欠点", "リスク", "悪化", "衰退", "デメリット", "バグ", "被害"]
        from datetime import datetime as _dt
        _cur_month = _dt.now().strftime("%B %Y")
        
        if any(kw in user_input for kw in market_keywords):
            search_needed = True
            has_rebound_query = any(w in q.lower() for q in search_queries for w in ["rebound", "recovery", "high", "反発", "回復"])
            if not has_rebound_query and len(search_queries) < 2:
                search_queries.append(f"semiconductor stock rebound recovery latest {_cur_month}")
                logger.info(f"📈 市場調査クエリにバランス反発検索クエリを自動追加しました: {search_queries[-1]}")
        elif search_needed and any(kw in user_input for kw in negative_keywords) and len(search_queries) < 2:
            # 市場以外のネガティブ単一問いに対して、改善・解決・最新フォローアップクエリを自動ペア補完
            search_queries.append(f"{search_queries[0]} solutions improvements latest update 2026")
            logger.info(f"⚖️ リサーチクエリに多角的バランス補完クエリを追加しました: {search_queries[-1]}")

        # --- Intent Routing (Auto Mode Switching) ---
        recommended_mode = search_plan.get("recommended_mode")
        if recommended_mode in ["chat", "task"]:
            mode = recommended_mode
            
        yield _sse_event({"type": "mode_switch", "mode": mode})
        
        # モード確定後にSupervisor用とExecutor用のプロンプトを個別に構築
        static_sys, dynamic_sys, persona_inst = build_system_instruction(
            user_input=user_input,
            mode=mode,
            mood=mood,
            filtered_kv_text=filtered_kv_text,
            followup_cooldown=followup_cooldown,
            kv_summary=kv_summary,
        )
        supervisor_sys_prompt = persona_inst + "\n\n" + static_sys
        supervisor_dynamic_sys = dynamic_sys
        
        executor_static, executor_dynamic, _ = build_system_instruction(
            user_input=user_input,
            mode=mode,
            mood=mood,
            filtered_kv_text="",  # Executorにはここで渡さない (memory_to_injectで注入する)
            followup_cooldown=followup_cooldown,
            kv_summary="",  # Executorには全記憶を絶対に渡さない（トークン節約＆ハルシネーション防止）
        )
        executor_sys_prompt = persona_inst + "\n\n" + executor_static
        executor_sys_prompt += "\n\n【ツール使用時の厳格なルール】\n<read_url>, <search>, <file>, <replace>, <run_command> 等のツールタグを出力した後は、**そのタグを出力した時点で即座にテキスト生成を停止し、システムからの実行結果の返却を待つこと。** 「実行中です」「スクレイピングしてくるわ」などの擬似的な演出テキストをタグの前後に追加することは絶対に禁止します。"
        executor_dynamic_sys = executor_dynamic
        
        if mode in ["task", "research"]:
            from app.routers.workspace import get_workspace_files_text
            workspace_text = get_workspace_files_text()
            user_input_with_context = f"{user_input}\n\n【現在のワークスペースのファイル（参考）】\n{workspace_text}"
        else:
            user_input_with_context = user_input
        
        search_results_text = None
        search_sources = []
        
        if search_needed:
            tasks = []
            max_queries = 2 # 検索API制限とコスト削減のため最大2クエリまでに制限（ユーザー指示）
            for q in search_queries[:max_queries]:
                yield _sse_event({"type": "status", "status": "searching", "query": q})
                tasks.append(web_search(q, providers=search_providers))
                logger.info(f"検索実行: '{q}' (Providers: {search_providers}) (Original: '{user_input}')")
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            combined_texts = []
            for i, res in enumerate(results):
                q = search_queries[i]
                if isinstance(res, Exception):
                    logger.error(f"検索実行エラー '{q}': {res}")
                else:
                    text, sources = res
                    combined_texts.append(f"【検索クエリ: {q}】\n{text}")
                    search_sources.extend(sources)
            
            # --- 🔴 P0: 検索失敗・不十分な場合の自動構造化クエリ再試行 (Sentinel 指示準拠) ---
            if not combined_texts or not any(len(t.strip()) > 50 for t in combined_texts):
                logger.warning("初回検索が不十分または空のため、構造化クエリ (site:指定、英語キーワード追加等) に切り替えて自動再試行します。")
                fallback_queries = []
                from datetime import datetime, timezone, timedelta
                _current_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
                for q in search_queries[:max_queries]:
                    # 質問がニュースや一般的なトピックの場合と、個別株の場合で構造化クエリをスマートに切り替え
                    if any(kw in user_input for kw in ["ニュース", "話題", "最新", "世界", "経済", "日本", "一般"]):
                        fallback_queries.append(f"{q} after:{_current_date}")
                        fallback_queries.append(f"{q} latest news July 2026")
                    else:
                        fallback_queries.append(f"{q} site:sec.gov OR site:finance.yahoo.com OR investor relations 2026")
                
                if fallback_queries:
                    retry_providers = ["news", "brave"] if any(kw in user_input for kw in ["ニュース", "話題", "最新", "一般"]) else ["brave", "finance"]
                    yield _sse_event({"type": "status", "status": "searching_retry", "query": fallback_queries[0]})
                    res_retry = await web_search(fallback_queries[0], providers=retry_providers)
                    if not isinstance(res_retry, Exception):
                        t_retry, s_retry = res_retry
                        if t_retry:
                            combined_texts.append(f"【構造化再検索クエリ: {fallback_queries[0]}】\n{t_retry}")
                            search_sources.extend(s_retry)

            # --- 🚀 改善案準拠: 自動スクレイピング昇格＆ディープフェッチパイプライン ---
            if search_sources:
                promoted_texts = []
                from app.core.search.router import fetch_url

                # 重要お知らせ検出キーワード（工事・休業・メンテナンス等）
                # 旅行日程に直接影響しうる施設側の通知を自動昇格で本文取得する
                CRITICAL_NOTICE_KEYWORDS = [
                    "工事", "メンテナンス", "休業", "臨時休館", "休止", "中止",
                    "運休", "お知らせ", "注意", "変更", "改装", "閉鎖",
                ]

                # 通常昇格候補（上位2件）
                normal_candidates = list(search_sources[:2])
                promoted_urls = {s.get("url", "") for s in normal_candidates}

                # 重要通知の追加昇格（3〜5件目をスキャン、最大1件追加）
                for src in search_sources[2:5]:
                    url = src.get("url", "")
                    if url in promoted_urls:
                        continue
                    title = src.get("title", "")
                    snippet = src.get("snippet", "")
                    combined_check = f"{title} {snippet}"
                    if any(kw in combined_check for kw in CRITICAL_NOTICE_KEYWORDS):
                        logger.info(f"🔔 重要お知らせ検出による追加昇格: {url} (Title: {title})")
                        normal_candidates.append(src)
                        promoted_urls.add(url)
                        break  # 追加は1件まで

                for src in normal_candidates:
                    url = src.get("url", "")
                    title = src.get("title", "")
                    snippet = src.get("snippet", "")
                    combined_check = f"{title} {snippet}"
                    # 昇格条件: 学術論文・技術記事・数値確認・100字未満スニペット・ニュース・重要お知らせ等
                    is_academic_or_tech = any(dom in url.lower() for dom in ["pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "arxiv.org", "ieee.org", "nature.com", "sciencedirect.com", "springer.com", "acm.org", "github.com"])
                    is_deep_query = any(kw in user_input for kw in ["論文", "成功率", "数値", "報告", "教え", "詳細", "攻撃", "防御", "パッチ", "スクレイピング", "記事", "読んで"])
                    is_critical_notice = any(kw in combined_check for kw in CRITICAL_NOTICE_KEYWORDS)
                    if len(snippet) < 200 or is_academic_or_tech or is_deep_query or is_critical_notice or any(kw in title for kw in ["今朝の", "5本", "Wrap", "Stories", "Digest", "まとめ", "ニュース"]):
                        logger.info(f"自動スクレイピング昇格実行: {url} (Title: {title}){' [重要お知らせ]' if is_critical_notice else ''}")
                        yield _sse_event({"type": "status", "status": "scraping_promotion", "url": url})
                        try:
                            scraped_content = await fetch_url(url)
                            if scraped_content and not scraped_content.startswith("❌") and len(scraped_content.strip()) > 50:
                                # 論文後半のDefense/結論セクションまで含めて最大15000字抽出（トークン爆発防止）
                                content_snippet = _extract_smart_snippet(scraped_content, 15000)
                                promoted_texts.append(f"【自動スクレイピング昇格本文: {title} ({url})】\n{content_snippet}")
                        except Exception as e:
                            logger.warning(f"自動スクレイピング昇格失敗 {url}: {e}")
                
                if promoted_texts:
                    combined_texts.extend(promoted_texts)

            # 最終的な検索結果テキストの結合とサイズクリップ
            if combined_texts:
                search_results_text = _clip_search_results("\n\n".join(combined_texts))

            if search_sources:
                # URLで重複排除
                unique_sources = []
                seen_urls = set()
                for s in search_sources:
                    if s["url"] not in seen_urls:
                        seen_urls.add(s["url"])
                        unique_sources.append(s)
                search_sources = unique_sources
                yield _sse_event({"type": "sources", "data": search_sources})
                
            # 自動スクレイピング（ディープサーチ）機能は、完全許可制ルールの導入に伴い無効化しました。
            # AIが明示的に許可を得て <read_url> を実行した場合のみスクレイピングが行われます。

        if direct_url_texts:
            existing_text = search_results_text or ""
            search_results_text = _clip_search_results(existing_text + "\n\n" + "\n\n".join(direct_url_texts))
            logger.info("ユーザー指定URLのスクレイピング本文をコンテキストに統合完了")

        max_supervisor_loops = 2
        supervisor_loop_count = 0
        escalation_history = []
        
        while supervisor_loop_count < max_supervisor_loops:
            supervisor_loop_count += 1
            
            # 2. 思考モデル (V4 Pro)
            yield _sse_event({"type": "status", "status": "thinking"})
            
            current_user_input_with_context = user_input_with_context
            if escalation_history:
                escalation_msg = "\n\n【Executorからの差し戻し（エスカレーション）情報】\n" + "\n---\n".join(escalation_history)
                current_user_input_with_context += escalation_msg
            
            # 🔴 LLM応答キャッシュチェック（Supervisor呼び出し前）
            from app.routers.settings import app_settings as settings_module
            _settings = settings_module.get()
            _provider = _settings.get("supervisor_provider", "deepseek")
            _model = _settings.get("supervisor_model", "deepseek-v4-flash")
            
            # ディープ調査・論文リサーチ・市場相場クエリ時は古いLLMキャッシュをバイパスして最新エンジンで実処理
            is_deep_query = any(kw in user_input for kw in ["論文", "成功率", "数値", "報告", "教え", "詳細", "攻撃", "防御", "パッチ", "スクレイピング", "記事", "読んで", "株", "相場", "半導体", "インテル", "AVGO", "最高値", "暴落", "市場", "経済"])
            if not is_deep_query:
                cached_response = await get_llm_cache(
                    user_input=current_user_input_with_context,
                    system_prompt=supervisor_sys_prompt,
                    mode=mode,
                    model=_model,
                    provider=_provider,
                    max_age_seconds=1800,
                )
            else:
                cached_response = None
            
            if cached_response:
                logger.info(f"⚡ Supervisorキャッシュヒット: {user_input[:30]}...")
                supervisor_json = cached_response["supervisor_json"]
                reasoning = cached_response.get("reasoning", "")
            else:
                try:
                    supervisor_json, reasoning = await run_supervisor(
                        user_input=current_user_input_with_context + "\n\n【動的システムコンテキスト】\n" + supervisor_dynamic_sys,
                        search_results=search_results_text,
                        memory_text=filtered_kv_text,
                        history_messages=messages,
                        mode=mode,
                        system_instruction=supervisor_sys_prompt,
                    )
                    # キャッシュに保存
                    await set_llm_cache(
                        user_input=current_user_input_with_context,
                        system_prompt=supervisor_sys_prompt,
                        mode=mode,
                        model=_model,
                        provider=_provider,
                        response=json.dumps(supervisor_json, ensure_ascii=False),
                        reasoning=reasoning,
                        supervisor_json=supervisor_json,
                        ttl_seconds=1800,
                    )
                except Exception as e:
                    logger.error(f"Supervisor error: {e}")
                    yield _sse_event({"type": "error", "message": str(e)})
                    return
            
            if reasoning:
                yield _sse_event({"type": "reasoning", "content": reasoning})

            # バックグラウンド処理: メモリ抽出 (Supervisorの判断を使用・Executor前に行う)
            kv_action = supervisor_json.get("kv_action")
            if kv_action and isinstance(kv_action, dict) and kv_action.get("action") in ["add", "update", "delete"]:
                try:
                    action = kv_action.get("action")
                    if action == "add":
                        kv_store.add(kv_action)
                        logger.info(f"Supervisor指示によるメモリ追加: {kv_action.get('summary', {}).get('target')}")
                    elif action == "update" and kv_action.get("target_id"):
                        target_id = int(kv_action["target_id"])
                        kv_store.update(target_id, kv_action)
                        logger.info(f"Supervisor指示によるメモリ更新: ID {target_id}")
                    elif action == "delete" and kv_action.get("target_id"):
                        target_id = int(kv_action["target_id"])
                        kv_store.delete(target_id)
                        logger.info(f"Supervisor指示によるメモリ削除: ID {target_id}")
                
                    # KVメモリが更新されたので、プロンプト用のテキストを再生成する
                    relevant_kv = kv_store.filter_by_scope(user_input)
                    filtered_kv_text = kv_store.format_for_prompt(relevant_kv)
                    if any(k in user_input for k in ["メモリ", "記憶", "覚えて", "KV", "プロフィール"]):
                        filtered_kv_text = "（ユーザーの記憶やプロフィールを確認する場合は <internal_kv_state> を参照してください）"
                    kv_summary = kv_store.format_summary()
                
                    # Supervisor向けにプロンプトを再構築 (エスカレーション再試行用)
                    retry_static, retry_dynamic = build_system_instruction(
                        user_input=user_input,
                        mode=mode,
                        mood=mood,
                        filtered_kv_text=filtered_kv_text,
                        followup_cooldown=followup_cooldown,
                        kv_summary=kv_summary,
                    )
                    supervisor_sys_prompt = retry_static
                    supervisor_dynamic_sys = retry_dynamic
                except Exception as e:
                    logger.error(f"SupervisorからのKV保存に失敗しました: {e}")

            # モードの強制上書き
            if supervisor_json.get("mode"):
                mode = supervisor_json["mode"]
                yield _sse_event({"type": "mode_switch", "mode": mode})
            
            if mode == "hearing":
                hearing_state = supervisor_json.get("hearing_state", {})
                next_q = hearing_state.get("next_question", "どうする？")
                if is_hyper_gal and next_q:
                    next_q = to_hyper_gal_v3(next_q)
                else:
                    yield _sse_event({"type": "chunk", "content": next_q})
                await _save_messages(
                    session_id, user_input, next_q, json.dumps(supervisor_json, ensure_ascii=False), supervisor_json, reasoning, search_sources
                )
                yield _sse_event({"type": "done", "content": next_q})
                return
            
            if mode == "spec_generation":
                spec_doc = supervisor_json.get("spec_document", {})
                surface = spec_doc.get("surface", "仕様書ができました。")
                if is_hyper_gal and surface:
                    surface = to_hyper_gal_v3(surface)
                else:
                    yield _sse_event({"type": "chunk", "content": surface})
                await _save_messages(
                    session_id, user_input, surface, json.dumps(supervisor_json, ensure_ascii=False), supervisor_json, reasoning, search_sources
                )
                yield _sse_event({"type": "done", "content": surface})
                return
            
            if mode == "coding":
                mode = "task" # 実行モデル向けにTaskモードとして扱う

            # プラン提示判定 (Planning Mode) — 承認フロー
            if supervisor_json.get("plan"):
                yield _sse_event({"type": "status", "status": "proposing_plan"})
                plan_content = supervisor_json["plan"]
                plan_text = f"<plan>\n{plan_content}\n</plan>\n\n---\n💡 **このプランで進めますか？** 「はい」「OK」「進めて」等で承認、または修正点があれば教えてください。"
                yield _sse_event({"type": "chunk", "content": plan_text})
                
                # プラン情報をDBに保存（次ターンで承認/修正を判定するため）
                await _save_messages(
                    session_id, user_input, plan_text, json.dumps(supervisor_json, ensure_ascii=False), supervisor_json, reasoning, search_sources
                )
                
                # plan_awaiting_approval 状態を設定
                from app.core.kv_store import kv_store
                try:
                    kv_store.add({
                        "action": "add",
                        "category": "agreement",
                        "quote": user_input[:40],
                        "summary": {
                            "target": "pending_plan",
                            "stance": "条件付き",
                            "note": f"承認待ちプラン: {plan_content[:100]}",
                            "tags": ["plan", "approval", "pending"]
                        }
                    })
                except Exception:
                    pass
                
                yield _sse_event({"type": "done", "content": plan_text})
                return

            # 内部仕様書の抽出 (過去の履歴から直近のものを探す)
            internal_spec = None
            for msg in messages:
                if msg.get("thinking_json"):
                    try:
                        parsed = json.loads(msg["thinking_json"])
                        if parsed.get("spec_document") and parsed["spec_document"].get("internal"):
                            internal_spec = parsed["spec_document"]["internal"]
                    except:
                        pass
            if supervisor_json.get("spec_document") and supervisor_json["spec_document"].get("internal"):
                internal_spec = supervisor_json["spec_document"]["internal"]
            
            if internal_spec and mode in ["coding", "task"]:
                executor_sys_prompt = f"<spec_internal>\n{internal_spec}\n</spec_internal>\n\n" + executor_sys_prompt

            # 沈黙判定（通常のchatモード等で、回答不要と判断された場合のみここで停止）
            if supervisor_json.get("silence"):
                yield _sse_event({"type": "done", "content": ""})
                await _save_messages(
                    session_id, user_input, "", json.dumps(supervisor_json, ensure_ascii=False), supervisor_json, reasoning, search_sources
                )
                return

            # 3. 自律実行ループ（Auto Execution Loop）
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
            memory_to_inject = filtered_kv_text if supervisor_json.get("memory_inject") else None
            search_to_inject = search_results_text if supervisor_json.get("search_used") else None
        
            # auto_execution_loop を使用した自律ループ
            from app.core.auto_execution_loop import auto_execute_with_retry
            
            sse_queue = asyncio.Queue()
            
            def _yield_sse(data: dict):
                """イベントストリームにyieldする内部関数"""
                nonlocal final_accumulated_response
                if data.get("type") == "chunk":
                    chunk_text = data.get("content", "")
                    final_accumulated_response += chunk_text
                    if is_hyper_gal:
                        return  # ギャルモード時は変換前の本文のchunkをSSEに送らず、完了時のギャル文字一括表示のみ行う
                sse_queue.put_nowait(data)
            
            yield _sse_event({"type": "status", "status": "responding"})
            
            try:
                exec_task = asyncio.create_task(
                    auto_execute_with_retry(
                        user_input=user_input_with_context,
                        instruction=instruction,
                        supervisor_sys_prompt=supervisor_sys_prompt,
                        supervisor_dynamic_sys=supervisor_dynamic_sys,
                        executor_sys_prompt=executor_sys_prompt,
                        executor_dynamic_sys=executor_dynamic_sys,
                        mode=mode,
                        session_id=session_id,
                        history_messages=messages,
                        search_results=search_to_inject,
                        memory_text=memory_to_inject,
                        max_tool_loops=40,
                        max_supervisor_retries=5,
                        yield_sse_func=_yield_sse,
                    )
                )
                
                while not exec_task.done() or not sse_queue.empty():
                    try:
                        item = await asyncio.wait_for(sse_queue.get(), timeout=0.05)
                        yield _sse_event(item)
                    except asyncio.TimeoutError:
                        continue
                
                ai_response, tool_results_summary, new_escalation = await exec_task
                escalation_history.extend(new_escalation)
            except Exception as e:
                logger.error(f"Auto execution loop error: {e}")
                yield _sse_event({"type": "error", "message": str(e)})
                return
            
            if escalation_history:
                continue  # supervisor loop retry

            # thinking データ（デバッグ/分析用）
            yield _sse_event({"type": "thinking", "data": supervisor_json})

            # 応答が空（0文字）の場合はエラーとして扱い、DBに保存しない（履歴汚染の防止）
            if not ai_response.strip():
                logger.error(f"⚠️ 最終生成応答が空のため、DB保存をスキップしてエラーイベントを送信します (session_id: {session_id})")
                yield _sse_event({"type": "error", "message": "応答の生成に失敗しました（出力が空です）。時間をおいてもう一度お試しください。"})
                return

            if is_hyper_gal and ai_response:
                ai_response = to_hyper_gal_v3(ai_response)

            # バックグラウンド処理: DB保存
            await _save_messages(
                session_id, user_input, ai_response, json.dumps(supervisor_json, ensure_ascii=False), supervisor_json, reasoning, search_sources
            )

            # フォローアップ履歴更新
            needs_followup = bool(supervisor_json.get("needs_followup")) if supervisor_json else False
            history.append(needs_followup)

            # 違反ログの記録 (検索スキップ等の判定)
            violation_risk = supervisor_json.get("violation_risk")
            if not violation_risk and search_needed and not supervisor_json.get("search_used"):
                violation_risk = "検索スキップ"
            
            if violation_risk:
                logger.warning(f"違反検出: {violation_risk} - session_id: {session_id}")
                # 本格的な違反ログDB保存は必要に応じて実装

            # 完了
            yield _sse_event({"type": "done", "content": ai_response})

            break  # supervisor loop break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _trim_history_content(content: str) -> str:
    if not content:
        return content

    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    content = re.sub(r'(?m)^(?:まず、ユーザーの発言を分析します[^\n]*\n+|Output format:[^\n]*\n+|user_intent_analysis:[^\n]*\n+)+', '', content)
    content = re.sub(r'【一般検索結果:.*?】\s*(?:\[brave\s*\[Tier.*?\]\].*?\n?)+', '', content, flags=re.DOTALL).strip()

    if len(content) < 4000:
        return content
    
    def replace_code_block(match):
        block = match.group(0)
        if len(block) > 800:
            lang = match.group(1) or ""
            return f"```{lang}\n(※過去の長大なコード/ログ出力一部省略)\n```"
        return block
    
    # あらゆる言語のコードブロック（```lang ... ```）にマッチさせる
    content = re.sub(r'```([a-zA-Z0-9_-]*)\s*[\s\S]*?```', replace_code_block, content)
    
    # さらに全体が4000文字を超える場合は冒頭と末尾を残して中間を圧縮
    if len(content) > 4000:
        content = content[:2000] + "\n\n(※過去の対話ログ一部省略)\n\n" + content[-2000:]
        
    return content


async def _get_conversation_messages(session_id: str) -> list[dict]:
    """DB からセッションの会話履歴を取得（トークン大量消費を防ぐため長大ブロックを自動トリミング）"""
    try:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT role, content, reasoning, search_sources, thinking_json FROM messages WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            )
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                msg = {
                    "role": row[0],
                    "content": _trim_history_content(row[1]),
                    "reasoning": row[2] if len(row) > 2 else None,
                }
                # sources が巨大な場合は None（57MB爆発防止）
                raw_sources = row[3] if len(row) > 3 and row[3] else None
                if raw_sources and len(str(raw_sources)) > 5000:
                    msg["sources"] = None
                else:
                    msg["sources"] = json.loads(raw_sources) if raw_sources else None
                # thinking_json が巨大な場合は None
                raw_thinking = row[4] if len(row) > 4 else None
                if raw_thinking and len(str(raw_thinking)) > 10000:
                    msg["thinking_json"] = None
                else:
                    msg["thinking_json"] = raw_thinking
                messages.append(msg)
            # 第2段階圧縮: 古いターンを圧縮（最新3ターン保持）
            return await compress_messages_stage2(messages, max_keep=3)
    except Exception as e:
        logger.error(f"履歴取得エラー: {e}")
        return []


def _trim_for_db(content: str, max_len: int = 30000) -> str:
    """DB保存用にコンテンツをトリミング（会話履歴の肥大化防止）"""
    if not content or len(content) <= max_len:
        return content
    half = max_len // 2
    return content[:half] + "\n\n(※システム保護のため一部省略)\n\n" + content[-half:]


async def _save_messages(
    session_id: str,
    user_message: str,
    ai_response: str,
    raw_response: str,
    json_data: dict | None,
    reasoning: str | None = None,
    search_sources: list[dict] | None = None,
):
    """ユーザーメッセージとAI応答をDBに保存（コンテンツは自動トリミング）"""
    try:
        async with get_db() as db:
            # DB保存前にトリミング（次回読み込み時の57MB爆発防止）
            trimmed_user = _trim_for_db(user_message)
            trimmed_ai = _trim_for_db(ai_response)
            trimmed_raw = _trim_for_db(raw_response, max_len=5000)
            # セッションが存在しない場合は作成（最初のメッセージからタイトルを生成）
            title = user_message[:30] + "..." if len(user_message) > 30 else user_message
            await db.execute(
                "INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)",
                (session_id, title),
            )

            # セッションのタイトルがnullの場合（新規作成API経由など）は更新する
            await db.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND title IS NULL",
                (title, session_id),
            )

            # ユーザーメッセージ（トリミング済み）
            await db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, trimmed_user),
            )

            # AI応答（トリミング済み）
            await db.execute(
                "INSERT INTO messages (session_id, role, content, raw_response, thinking_json, reasoning, search_sources) "
                "VALUES (?, 'assistant', ?, ?, ?, ?, ?)",
                (
                    session_id,
                    trimmed_ai,
                    trimmed_raw,
                    json.dumps(json_data, ensure_ascii=False) if json_data else None,
                    reasoning,
                    json.dumps(search_sources, ensure_ascii=False) if search_sources else None
                ),
            )

            # セッションの updated_at を更新
            await db.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,),
            )

            await db.commit()
            # 会話内容からの自動KVメモリ抽出・保存を非同期バックグラウンドで必ず実行する
            asyncio.create_task(extract_and_save_memory(session_id, user_message, ai_response))
    except Exception as e:
        logger.error(f"メッセージ保存エラー: {e}")