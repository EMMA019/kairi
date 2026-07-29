"""
内部マークアップ（think / ツールタグ）の除去と、途切れ検知。
ユーザー本文に XML・思考ログが漏れないようにする。
"""
from __future__ import annotations

import re
from typing import Tuple
from app.utils.logger import get_logger

logger = get_logger(__name__)

TOOL_TAG_NAMES = (
    r"file|replace|edit|run_command|read_url|read_file|list_dir|search|search_news|"
    r"search_codebase|grep_search|view_file|mcp_call|escalate"
)

_TOOL_OPEN = re.compile(rf"<(?:{TOOL_TAG_NAMES})\b", re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think\s*>", re.IGNORECASE)


def strip_internal_markup(text: str) -> str:
    """
    think / ツールXML（完全・不完全）・孤児閉じタグを除去する。
    """
    if not text or not isinstance(text, str):
        return text

    original = text

    # 完全な think ブロック
    text = re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 未閉じ think（末尾まで）
    text = re.sub(r"<think\b[^>]*>(?:(?!</think).)*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 孤児 </think>
    text = _THINK_CLOSE.sub("", text)

    # 完全なツールタグ（自己閉じ）
    text = re.sub(
        rf"<(?:{TOOL_TAG_NAMES})\b[^>]*/>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 完全な開閉タグ
    text = re.sub(
        rf"<(?:{TOOL_TAG_NAMES})\b[^>]*>.*?</(?:{TOOL_TAG_NAMES})\s*>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # 未閉じツール開始タグ（`>` 無しで行末または文字列末尾）
    text = re.sub(
        rf"<(?:{TOOL_TAG_NAMES})\b[^>\n]*$",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # 開きだけ残ったタグ（`>` あり・閉じなし）をタグごと除去
    text = re.sub(
        rf"<(?:{TOOL_TAG_NAMES})\b[^>]*>[^<]*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(rf"</(?:{TOOL_TAG_NAMES})\s*>", "", text, flags=re.IGNORECASE)

    # バッククォート1個だけの残骸行
    text = re.sub(r"(?m)^\s*`\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    cleaned = text.strip()
    if cleaned != original.strip():
        logger.info("🧹 内部マークアップ（think/ツールタグ）を除去しました")
    return cleaned


def looks_incomplete_output(text: str) -> bool:
    """継続生成が必要そうな不完全出力かどうか。"""
    if not text or not isinstance(text, str):
        return False
    s = text.rstrip()
    if not s:
        return False

    if _THINK_OPEN.search(s) and not _THINK_CLOSE.search(s):
        return True
    if _TOOL_OPEN.search(s):
        # 開いたツールタグが閉じられていない
        opens = len(_TOOL_OPEN.findall(s))
        closes = len(re.findall(rf"</(?:{TOOL_TAG_NAMES})\s*>", s, flags=re.IGNORECASE))
        self_closes = len(re.findall(rf"<(?:{TOOL_TAG_NAMES})\b[^>]*/>", s, flags=re.IGNORECASE))
        if opens > closes + self_closes:
            return True

    if s.count("```") % 2 == 1:
        return True

    last_line = s.splitlines()[-1].rstrip()

    # 単独バッククォート / 未閉じインラインコード残骸
    if re.match(r"^\s*`\s*$", last_line):
        return True
    # 奇数個のインラインバッククォートで終わる（フェンスは上記で処理済み）
    if last_line.count("`") % 2 == 1 and "```" not in last_line:
        return True

    # Markdown 表の途中切れ（| 始まりでセル未完、または末尾が裸バッククォート）
    if last_line.lstrip().startswith("|"):
        cells = [c.strip() for c in last_line.strip("|").split("|")]
        if any(c.endswith("`") and c.count("`") % 2 == 1 for c in cells):
            return True
        # 閉じ `|` がなく途中で切れている、またはセルが空で異常に短い
        if not last_line.rstrip().endswith("|") and len(last_line) > 2:
            return True
        if cells and cells[-1] == "" and last_line.count("|") >= 2:
            # "| foo | `" のような途中切れ
            if "`" in last_line:
                return True

    # コードっぽい途中切れ
    if re.search(
        r"(?:^|\n)\s*(?:if|for|while|def|class|return|import|from|elif|else)\b.*[:=\(\{\[]\s*$",
        last_line,
    ):
        return True
    if re.search(r"[=+\-*/%<>]$", last_line) and not last_line.strip().startswith("#"):
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", last_line) and len(last_line) <= 40:
        # 単独識別子で終わる（例: lag）
        if len(s.splitlines()) >= 3:
            return True

    # 日本語本文が句点・閉じ括弧なしで終わる（短文挨拶は除外）
    _TERMINALS = set("。．！？!?…‼⁉」』）)]\"'”’")
    if len(s) >= 40 and s[-1] not in _TERMINALS and not last_line.startswith("```"):
        # 英数字のみの識別子やURL末尾は除外
        if re.search(r"[ぁ-んァ-ン一-龥]", last_line):
            return True

    return False


def sanitize_preserving_body(text: str, sanitize_fn) -> str:
    """
    sanitize_fn 適用後に空になったら、マークアップ除去のみのスナップショットへ戻す。
    「掃除で本文ゼロ」を禁止する。
    """
    if not text or not isinstance(text, str):
        return text
    pre = text
    markup_only = strip_internal_markup(pre)
    try:
        after = sanitize_fn(pre)
    except Exception as e:
        logger.warning(f"sanitize_preserving_body: sanitize failed: {e}")
        return markup_only
    if after and after.strip():
        return after
    if markup_only and markup_only.strip():
        logger.warning("⚠️ サニタイズ後に空になったため、マークアップ除去版を復元します")
        return markup_only
    return after if after is not None else ""


def clean_assistant_visible(text: str) -> str:
    """loop_history 復元用: ツールXMLを落として可視本文だけ残す。"""
    if not text:
        return ""
    cleaned = strip_internal_markup(text)
    cleaned = re.sub(r"<[^>]+>.*?</[^>]+>|<[^>]+/>", "", cleaned, flags=re.DOTALL).strip()
    return cleaned
