"""
引用契約（Citation Contract）検証ステージ。

時事的な固有名詞・数値断定に検索結果番号 [n] が付いていない場合、
不確実表現へ変換するか除去する。正規表現パッチ群を段階的に置き換える中核。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CitationMetrics:
    truncation_detected: int = 0
    trim_applied: int = 0
    uncited_assertions: int = 0
    citations_found: int = 0


# プロセスローカルな直近メトリクス（integrity_stats 保存用）
_last_metrics = CitationMetrics()


def get_last_citation_metrics() -> CitationMetrics:
    return _last_metrics


def reset_citation_metrics() -> None:
    global _last_metrics
    _last_metrics = CitationMetrics()


_CITATION_RE = re.compile(r"\[(\d{1,3})\]")
# 区切り文字（句点）は保持し、後続空白は各パートに残す（改行崩壊防止）
_SENTENCE_SPLIT = re.compile(r"(?<=[。．！？!?…])")

# 時事・固有断定っぽいキーワード（文単位で引用必須のトリガ）
_ASSERTION_TRIGGERS = re.compile(
    r"(?:騎手|議長|CEO|監督|優勝|制覇|終値|オッズ|配当|契約|利下げ|利上げ|"
    r"ポイント|％|%|億ドル|億円|万ドル|"
    r"氏|さんが|が発表|と報じ|によると)"
)

# よくあるハルシネーション固有名（ソース照合用の追加チェック）
_KNOWN_RISKY_NAMES = [
    "ムーア", "Moore", "パウエル", "Powell", "イエレン", "Yellen",
]


def _source_has(name: str, source_text: str) -> bool:
    if not source_text:
        return False
    if name in source_text:
        return True
    # 簡易正規化
    return name.lower() in source_text.lower()


def verify_citations(
    text: str,
    source_text: str = "",
    *,
    soften_uncited: bool = True,
) -> str:
    """
    引用契約の検証。
    - ソースにない既知リスク固有名を除去/不確実化
    - 時事断定文に [n] が無い場合は文末に「（要確認）」を付与
    """
    global _last_metrics
    if not text or not isinstance(text, str):
        return text

    metrics = CitationMetrics()
    metrics.citations_found = len(_CITATION_RE.findall(text))

    # 1) ソースにない既知リスク固有名
    for name in _KNOWN_RISKY_NAMES:
        if name in text and not _source_has(name, source_text or ""):
            metrics.uncited_assertions += 1
            if soften_uncited:
                # 当該固有名を含む短文を不確実化
                pattern = re.compile(
                    rf"([^。．！？\n]*{re.escape(name)}[^。．！？\n]*[。．！？]?)"
                )

                def _soften(m: re.Match) -> str:
                    s = m.group(1)
                    if "要確認" in s or "未確認" in s:
                        return s
                    # 固有名を役職・一般表現へ置換できる場合は落とす
                    replaced = s.replace(name, "（氏名はソース未記載）")
                    if not replaced.rstrip().endswith(("。", "！", "？", "!", "?")):
                        replaced = replaced.rstrip() + "。"
                    if "要確認" not in replaced:
                        replaced = replaced.rstrip("。") + "（要確認）。"
                    return replaced

                text = pattern.sub(_soften, text)
                logger.info(f"📎 ソース未記載の固有名を不確実化: {name}")

    # 2) ソースにない絶対数値（終値ポイント等）→ 末尾免責
    if source_text is not None:
        abs_nums = re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text)
        unverified_abs = []
        for num in abs_nums:
            digits = num.replace(",", "")
            if num in (source_text or "") or digits in (source_text or ""):
                continue
            unverified_abs.append(num)
        if unverified_abs:
            metrics.uncited_assertions += len(set(unverified_abs))
            if soften_uncited and "※一部の比率" not in text and "※正確な" not in text and "公式開示" not in text:
                text = text.rstrip() + (
                    "\n\n※一部の比率・市場指標や価格等はソース記事に明記されていない"
                    "推計または周辺参考データを含む場合があります。"
                    "正確な最新数値は公式開示データをご確認ください。"
                )
                logger.info(f"📎 ソース未記載の絶対数値を検知し免責を付与: {unverified_abs[:5]}")

    # 3) 時事断定トリガ文に引用が無い場合
    if soften_uncited and (source_text or "").strip():
        parts = _SENTENCE_SPLIT.split(text)
        new_parts = []
        for part in parts:
            if not part or not part.strip():
                new_parts.append(part)
                continue
            has_trigger = bool(_ASSERTION_TRIGGERS.search(part))
            has_cite = bool(_CITATION_RE.search(part))
            if has_trigger and not has_cite and "要確認" not in part and "未確認" not in part:
                metrics.uncited_assertions += 1
                softened = part.rstrip()
                if softened.endswith(("。", "．", "!", "？", "?", "！")):
                    softened = softened[:-1] + "（要確認）" + softened[-1]
                else:
                    softened = softened + "（要確認）"
                new_parts.append(softened)
                logger.debug(f"📎 引用なし時事断定を不確実化: {part[:40]!r}")
            else:
                new_parts.append(part)
        text = "".join(new_parts)

    _last_metrics = metrics
    return text


def record_trim_metric(applied: bool = True) -> None:
    global _last_metrics
    if applied:
        _last_metrics.trim_applied += 1


def record_truncation_metric() -> None:
    global _last_metrics
    _last_metrics.truncation_detected += 1
