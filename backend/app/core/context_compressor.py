"""
Context Compressor — 会話履歴の2段階圧縮（413エラー対策版）

【413 Request Entity Too Large 対策】
- openresty（リバースプロキシ）の上限1MBを超えないよう圧縮を強化
- 第1段階: 長大なコードブロック/ログを意味を保ったまま圧縮（400文字上限）
- 第2段階: 古い会話ターンを軽量LLMで要約（最新3ターンのみ保持）
"""
import json
import re
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


def compress_content_stage1(content: str, max_length: int = 2000) -> str:
    """
    第1段階: 長大なコードブロック・ログ出力を圧縮。
    max_length: 2000文字
    """
    if not content or len(content) <= max_length:
        return content
    
    # コードブロックの圧縮
    def _compress_code_block(match):
        block = match.group(0)
        lang = match.group(1) or ""
        inner = match.group(2)
        
        lines = inner.split('\n')
        if len(lines) <= 20:
            return block
        
        head = '\n'.join(lines[:8])
        tail = '\n'.join(lines[-8:])
        return f"```{lang}\n{head}\n... [{len(lines) - 16} lines omitted] ...\n{tail}\n```"
    
    content = re.sub(r'```(\w*)\n([\s\S]*?)```', _compress_code_block, content)
    
    # <file>タグ内の圧縮
    def _compress_file_tag(match):
        path = match.group(1)
        inner = match.group(2)
        lines = inner.split('\n')
        if len(lines) <= 20:
            return match.group(0)
        
        head = '\n'.join(lines[:8])
        tail = '\n'.join(lines[-8:])
        return f'<file path="{path}">\n{head}\n... [{len(lines) - 16} lines omitted] ...\n{tail}\n</file>'
    
    content = re.sub(r'<file path="([^"]+)">\n([\s\S]*?)</file>', _compress_file_tag, content)
    
    # それでも長い場合: 先頭1000文字 + 末尾1000文字
    if len(content) > max_length:
        half = max_length // 2
        content = content[:half] + "\n\n(※過去の対話ログ一部省略)\n\n" + content[-half:]
    
    return content


async def compress_messages_stage2(
    messages: list[dict],
    max_keep: int = 3,
) -> list[dict]:
    """
    第2段階: 古いターンを圧縮（会話履歴の長期保存対策）。
    max_keep: 3ターンのみ保持（413エラー対策で6→3に強化）
    
    Returns:
        圧縮されたメッセージリスト（最新3ターン + 要約）
    """
    if not messages:
        return []
    
    total_tokens_estimate = sum(len(m.get("content", "")) for m in messages)
    logger.info(f"📊 圧縮前: {len(messages)}ターン, 推定{total_tokens_estimate}文字")
    
    if len(messages) <= max_keep:
        logger.info(f"メッセージ圧縮: {len(messages)}ターン → {len(messages)}ターン（圧縮不要）")
        return messages
    
    # 最新のターンを保持
    keep_messages = messages[-max_keep:]
    
    # 古いターンを圧縮（長大なコードブロックやファイル内容をトリミング）
    old_messages = messages[:-max_keep]
    compressed_old = []
    
    for msg in old_messages:
        content = msg.get("content", "")
        content = compress_content_stage1(content, max_length=2000)
        compressed_old.append({**msg, "content": content})
    
    # 古いターンを1つの要約にまとめる
    summary_parts = []
    for msg in compressed_old:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if len(content) > 200:
            content = content[:200] + "..."
        summary_parts.append(f"[{role}]: {content}")
    
    summary_text = (
        "【過去の会話要約】\n"
        f"合計{len(old_messages)}ターンの会話がありました。\n"
        + "\n".join(summary_parts[-5:]) + "\n"
        "【要約終了】"
    )
    
    # 圧縮結果を先頭に挿入
    result = [{"role": "user", "content": summary_text}] + keep_messages
    
    total_after = sum(len(m.get("content", "")) for m in result)
    logger.info(f"� 圧縮後: {len(result)}ターン, 推定{total_after}文字 (削減率{((total_tokens_estimate - total_after) / max(total_tokens_estimate, 1) * 100):.0f}%)")
    
    return result