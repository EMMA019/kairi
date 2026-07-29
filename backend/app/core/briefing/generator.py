"""
ブリーフィング生成 — ローリングプールから下書き Markdown を作る。

寄り前 JST 08:15 / 大引け後 JST 16:00。
外部への自動公開はせず、storage/briefings/ に保存して目視確認用とする。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

JST = timezone(timedelta(hours=9))
BriefKind = Literal["preopen", "postclose"]

BRIEFING_DIR = Path(__file__).resolve().parents[3] / "storage" / "briefings"


def _now_jst() -> datetime:
    return datetime.now(JST)


async def _score_and_rank(items: list[dict], top_k: int = 5) -> list[dict]:
    from app.core.monitor.watchlist import systematic_screen_and_score, systematic_deduplicate

    scored = [systematic_screen_and_score(dict(it)) for it in items]
    scored.sort(key=lambda x: x.get("importance", 0), reverse=True)

    kept: list[dict] = []
    for c in scored:
        if c.get("importance", 0) < 50 and len(kept) >= 1:
            # 閾値未満は後段補充で扱う
            continue
        is_dup, _ = await systematic_deduplicate(c, kept)
        if not is_dup and c.get("importance", 0) >= 50:
            kept.append(c)
        if len(kept) >= top_k:
            return kept

    if len(kept) < top_k:
        for c in scored:
            if c in kept:
                continue
            is_dup, _ = await systematic_deduplicate(c, kept)
            if not is_dup:
                kept.append(c)
            if len(kept) >= top_k:
                break
    return kept


def _format_story(item: dict, idx: int) -> str:
    title = (item.get("title") or "").strip()
    source = (item.get("source") or "").strip()
    url = (item.get("url") or "").strip()
    summary = (item.get("summary") or item.get("companion_summary") or "").strip()
    # HTMLタグ簡易除去
    import re

    summary = re.sub(r"<[^>]+>", "", summary)
    if len(summary) > 280:
        summary = summary[:280] + "…"

    lines = [f"### {idx}. {title}"]
    if item.get("companion_url"):
        lines.append(
            f"- 初出（ペイウォール）: [{source}]({url})"
            if url
            else f"- 初出（ペイウォール）: {source}"
        )
        lines.append(
            f"- 無料ソース: [{item.get('companion_source') or 'free'}]({item['companion_url']})"
        )
        if item.get("companion_summary"):
            cs = re.sub(r"<[^>]+>", "", item["companion_summary"])
            lines.append(f"- 要旨: {cs[:280]}")
    else:
        if url:
            lines.append(f"- 出典: [{source}]({url})")
        else:
            lines.append(f"- 出典: {source}")
        if summary:
            lines.append(f"- 要旨: {summary}")

    importance = item.get("importance")
    if importance is not None:
        lines.append(f"- 重要度スコア: {importance}")
    catalysts = item.get("detected_catalysts") or []
    if catalysts:
        lines.append(f"- カタリスト: {', '.join(catalysts[:3])}")
    return "\n".join(lines)


def _jp_snapshot_section() -> str:
    try:
        from app.core.tools.market_data import format_jp_market_snapshot_for_prompt

        text = format_jp_market_snapshot_for_prompt("日本市場スナップショット")
        if text and text.strip():
            return "## 日本市場スナップショット\n\n" + text.strip() + "\n"
    except Exception as e:
        logger.warning(f"JP snapshot for briefing failed: {e}")
    return "## 日本市場スナップショット\n\n（取得失敗または休場）\n"


def render_briefing_markdown(
    kind: BriefKind,
    stories: list[dict],
    *,
    calendar_text: str = "",
    include_jp_snapshot: bool = False,
    generated_at: Optional[datetime] = None,
) -> str:
    now = generated_at or _now_jst()
    label = "寄り前ブリーフ" if kind == "preopen" else "大引け後ブリーフ"
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M JST")

    parts = [
        f"# Kairi {label} — {date_str}",
        f"生成時刻: {time_str}",
        "",
        "> 下書き。配信前に目視確認すること。投資助言ではありません。数値・日付は出典と照合済みの範囲のみ記載。",
        "",
    ]

    if calendar_text:
        parts.append("## 市場カレンダー")
        parts.append("")
        parts.append(calendar_text.strip())
        parts.append("")

    if include_jp_snapshot:
        parts.append(_jp_snapshot_section())
        parts.append("")

    parts.append("## 注目ヘッドライン")
    parts.append("")
    if not stories:
        parts.append("（該当時間のプールに注目記事がありませんでした）")
    else:
        for i, s in enumerate(stories, 1):
            parts.append(_format_story(s, i))
            parts.append("")

    parts.append("---")
    parts.append(
        "免責: 本ブリーフは公開情報の要約であり投資助言ではありません。"
        "ペイウォール記事は無料ソースで裏取りした範囲のみ事実として扱います。"
    )
    return "\n".join(parts).strip() + "\n"


async def generate_briefing(
    kind: BriefKind,
    *,
    dry_run: bool = False,
    hours: Optional[float] = None,
) -> dict[str, Any]:
    """
    プールから記事を取り、スコアリング・ペイウォール差し替え・フィルタ後に保存。
    """
    from app.core.news.database import get_pool_news, init_db as init_news_db
    from app.core.news.paywall import attach_companions
    from app.core.market_calendar import format_market_status
    from app.core.fact_filters.pipeline import apply_grounding_pipeline

    await init_news_db()

    if hours is None:
        hours = 18.0 if kind == "preopen" else 10.0

    pool = await get_pool_news(hours=hours, limit=250)
    logger.info(f"📝 briefing[{kind}] pool={len(pool)} hours={hours}")

    stories = await _score_and_rank(pool, 5)
    stories = await attach_companions(stories, max_lookups=5)

    calendar_text = format_market_status()
    include_snap = kind == "postclose"
    raw_md = render_briefing_markdown(
        kind,
        stories,
        calendar_text=calendar_text,
        include_jp_snapshot=include_snap,
    )

    # 出典コンテキスト: タイトル+サマリ+companion
    source_blob = "\n".join(
        f"{s.get('title','')}\n{s.get('summary','')}\n{s.get('companion_summary','')}"
        for s in stories
    )
    filtered_md = apply_grounding_pipeline(raw_md, source_blob, user_input="市場ブリーフィング")

    now = _now_jst()
    filename = f"{now.strftime('%Y-%m-%d')}_{kind}.md"
    out_path = BRIEFING_DIR / filename
    if not dry_run:
        BRIEFING_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(filtered_md, encoding="utf-8")
        logger.info(f"📝 briefing saved: {out_path}")

        # Discord へ任意送信（Webhook未設定なら dry-run ログのみ）
        try:
            await _maybe_notify_discord(kind, filtered_md, stories)
        except Exception as e:
            logger.warning(f"briefing discord notify failed: {e}")

    return {
        "kind": kind,
        "path": str(out_path),
        "story_count": len(stories),
        "pool_count": len(pool),
        "markdown": filtered_md,
        "dry_run": dry_run,
    }


async def _maybe_notify_discord(kind: BriefKind, markdown: str, stories: list[dict]) -> None:
    """既存 Discord 基盤を流用。Webhook が無ければログのみ。"""
    from app.core.notify.discord import send_discord_alert

    title = stories[0].get("title") if stories else f"Kairi {kind} briefing"
    item = {
        "title": f"[Briefing:{kind}] {title}",
        "summary": markdown[:1500],
        "url": "",
        "source": "Kairi Briefing",
        "importance": 80,
        "matched_targets": [],
        "matched_entities": [],
        "detected_catalysts": ["ブリーフィング"],
        "score_reasons": [],
    }
    # dry_run=False でも webhook 未設定なら内部でログのみ
    await send_discord_alert(item, dry_run=False)
