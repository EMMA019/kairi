"""文末に張り付いた Markdown ブロックの改行補完。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.fact_filters.format import ensure_markdown_block_breaks


def test_heading_after_period():
    text = "好材料が重なったタイミングです。## 🟢 いいニュース・好材料 (Bull Cases)"
    out = ensure_markdown_block_breaks(text)
    assert "です。\n\n## 🟢" in out


def test_list_after_period():
    text = "株価は以下の通りです。- SNDK: $1,567.50"
    out = ensure_markdown_block_breaks(text)
    assert "です。\n\n- SNDK" in out


def test_hr_after_period():
    text = "以下、材料を整理します。---"
    out = ensure_markdown_block_breaks(text)
    assert "します。\n\n---" in out


def test_price_range_untouched():
    text = "想定レンジは100-200ドルです。"
    assert ensure_markdown_block_breaks(text) == text


def test_already_spaced_unchanged():
    text = "結論です。\n\n## 見出し\n本文"
    assert ensure_markdown_block_breaks(text) == text
