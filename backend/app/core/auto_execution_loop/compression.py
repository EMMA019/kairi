from app.utils.logger import get_logger
from .heuristics import _detect_error

logger = get_logger(__name__)

async def _smart_compress_loop_history(
    loop_history: list[dict],
    max_total_chars: int = 30000,
    *,
    session_id: str | None = None,
) -> list[dict]:
    """ツール結果の重要度に基づいた賢い圧縮（Claude Code準拠）。

    何を落としたかを明示ログ（＋任意で session_events）に残す。
    """
    if len(loop_history) <= 6:
        return loop_history[:-1]  # 最新3ターン以内ならそのまま返す（最後の要素は別途処理されるため除外）
        
    recent = loop_history[-6:-1]  # 直近3ターン（最新の入力除く）は完全保持
    older = loop_history[:-6]
    
    compressed = []
    actions: list[dict] = []
    for idx, msg in enumerate(older):
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        original_len = len(content)
        
        if role == "assistant":
            # 生成コードは模倣防止のため保持
            compressed.append(msg)
            actions.append({"index": idx, "role": role, "action": "keep", "reason": "assistant"})
        else:
            # ツール結果の重要度判定
            has_error = _detect_error(content) is not None or "【テスト失敗】" in content or "エラー" in content
            is_file_read = "ファイル読み込み成功" in content or "📄" in content
            
            if has_error:
                compressed.append(msg)
                actions.append({"index": idx, "role": role, "action": "keep", "reason": "error_context", "chars": original_len})
            elif is_file_read and len(content) <= 3000:
                compressed.append(msg)
                actions.append({"index": idx, "role": role, "action": "keep", "reason": "file_read_short", "chars": original_len})
            elif len(content) > 500:
                compressed.append({
                    "role": role,
                    "content": content[:200] + f"\n...[ツール結果 ({len(content)}文字) キャッシュ効率・重要度判定により圧縮]...\n" + content[-200:]
                })
                actions.append({
                    "index": idx,
                    "role": role,
                    "action": "truncate",
                    "reason": "long_tool_result",
                    "chars_before": original_len,
                    "chars_after": 400 + len(str(len(content))),
                })
            else:
                compressed.append(msg)
                actions.append({"index": idx, "role": role, "action": "keep", "reason": "short", "chars": original_len})

    dropped_or_truncated = [a for a in actions if a.get("action") != "keep"]
    if dropped_or_truncated:
        logger.info(
            "🗜️ loop compaction: older=%d kept_recent=%d changed=%d detail=%s",
            len(older),
            len(recent),
            len(dropped_or_truncated),
            dropped_or_truncated[:8],
        )
        if session_id:
            try:
                from app.core.session_events import append_event

                append_event(
                    session_id,
                    "compaction",
                    {
                        "older_count": len(older),
                        "recent_kept": len(recent),
                        "actions": dropped_or_truncated[:20],
                    },
                )
            except Exception as e:
                logger.debug("compaction session_event skipped: %s", e)
                
    return compressed + recent
