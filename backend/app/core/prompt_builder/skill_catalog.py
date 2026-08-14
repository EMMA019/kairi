"""Skill catalog + on-demand loader (dsh-inspired: don't dump full SKILL.md into every prompt)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Tuple

from app.utils.logger import get_logger
from app.core.prompt_builder.skill_meta import parse_skill_frontmatter, skill_matches

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = BASE_DIR / "skills"

_last_digest: dict[str, str] = {}


def list_skill_entries() -> List[dict]:
    """Return metadata for every skill folder that has SKILL.md."""
    if not SKILLS_DIR.exists():
        return []
    out: List[dict] = []
    for skill_folder in sorted(SKILLS_DIR.iterdir(), key=lambda p: p.name):
        if not skill_folder.is_dir():
            continue
        skill_file = skill_folder / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8")
            meta, _body = parse_skill_frontmatter(content)
            out.append(
                {
                    "id": skill_folder.name,
                    "name": meta.get("name") or skill_folder.name,
                    "description": meta.get("description") or "",
                    "keywords": meta.get("keywords") or [],
                    "path": str(skill_file),
                }
            )
        except Exception as e:
            logger.warning("Failed to list skill %s: %s", skill_folder.name, e)
    return out


def matching_skill_ids(user_input: str) -> List[str]:
    """Skill ids whose keywords match the user input (catalog hint only)."""
    matched = []
    for entry in list_skill_entries():
        if skill_matches(user_input or "", entry["id"], entry.get("keywords") or []):
            matched.append(entry["id"])
    return matched


def catalog_digest(user_input: str = "") -> str:
    """sha256 of id+description pairs (+ matched set) for hot-refresh detection."""
    entries = list_skill_entries()
    matched = matching_skill_ids(user_input)
    parts = [f"{e['id']}|{(e.get('description') or '').strip()}" for e in entries]
    parts.append("matched:" + ",".join(sorted(matched)))
    blob = "\\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def load_skill_body(skill_id: str) -> Tuple[bool, str]:
    """Load full SKILL.md body by folder id. Returns (ok, text)."""
    if not skill_id or not isinstance(skill_id, str):
        return False, "[ERROR] skill_id が空です"
    safe = skill_id.strip().replace("\\", "/").split("/")[-1]
    skill_file = SKILLS_DIR / safe / "SKILL.md"
    if not skill_file.exists():
        known = ", ".join(e["id"] for e in list_skill_entries()) or "(none)"
        return False, f"[ERROR] 不明なスキル: {safe}。利用可能: {known}"
    try:
        content = skill_file.read_text(encoding="utf-8")
        meta, body = parse_skill_frontmatter(content)
        display = meta.get("name") or safe
        text = f"### 【Loaded Skill: {display}】\\n" + (body or content)
        return True, text
    except Exception as e:
        return False, f"[ERROR] スキル読込失敗 ({safe}): {e}"


def build_skill_catalog_prompt(user_input: str = "") -> str:
    """
    Inject a short catalog into the system prompt instead of full skill bodies.
    Matching skills are marked as recommended; the model must call load_skill to read them.
    """
    entries = list_skill_entries()
    if not entries:
        return ""
    matched = set(matching_skill_ids(user_input))
    digest = catalog_digest(user_input)
    lines = [
        f"<!-- catalog_digest: {digest} -->",
        "# 【スキルカタログ（全文は自動注入しない）】",
        "専門スキルが必要なときだけ <mcp_call tool=\"load_skill\" skill_id=\"...\" /> で本文を読み込むこと。",
        "マッチしたスキルは推奨。無関係なスキルは読まない。",
        "",
    ]
    for e in entries:
        flag = " ←推奨（入力にマッチ）" if e["id"] in matched else ""
        desc = (e.get("description") or "").strip()
        if len(desc) > 120:
            desc = desc[:117] + "..."
        lines.append(f"- {e['id']}: {desc}{flag}")
    return "\\n".join(lines)


def maybe_catalog_refresh_message(session_id: str, user_input: str = "") -> str:
    """
    If the skill catalog digest changed since last turn for this session,
    return a user-role style refresh block; otherwise empty string.
    First sighting only stores digest (no refresh noise).
    """
    sid = (session_id or "").strip() or "unknown"
    digest = catalog_digest(user_input)
    prev = _last_digest.get(sid)
    _last_digest[sid] = digest
    if prev is None or prev == "":
        return ""
    if prev == digest:
        return ""
    try:
        from app.core.session_events import append_event

        append_event(
            sid,
            "skill/catalog_refresh",
            {"prev": prev, "digest": digest},
        )
    except Exception as e:
        logger.warning("catalog_refresh event failed: %s", e)
    prompt = build_skill_catalog_prompt(user_input)
    return (
        "【スキルカタログ更新】カタログ内容が変わりました。最新の一覧を参照してください。\\n\\n"
        + prompt
    )
