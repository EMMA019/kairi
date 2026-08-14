import json
import re
from datetime import datetime
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"

def load_prompt(filename: str) -> str:
    """指定されたMarkdownファイルを読み込んで返す"""
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        # エラーを握りつぶさず、ログに出すか例外を投げる設計
        logger.warning(f"Prompt file not found: {file_path}")
        return ""
    
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def load_active_skills(user_input: str) -> str:
    """Inject a short skill catalog (not full SKILL.md bodies).

    Full bodies are loaded on demand via the `load_skill` tool to keep the
    static/dynamic prompt cache stable and avoid dumping unrelated skills.
    """
    try:
        from .skill_catalog import build_skill_catalog_prompt

        return build_skill_catalog_prompt(user_input or "")
    except Exception as e:
        logger.warning(f"Failed to build skill catalog: {e}")
        return ""


def load_active_skills_full(user_input: str) -> str:
    """Legacy: inject full matched SKILL.md bodies (tests / opt-in only)."""
    skills_dir = BASE_DIR / "skills"
    if not skills_dir.exists():
        return ""

    from .skill_meta import parse_skill_frontmatter, skill_matches

    active_skills = []
    for skill_folder in skills_dir.iterdir():
        if not skill_folder.is_dir():
            continue
        skill_file = skill_folder / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8")
            meta, body = parse_skill_frontmatter(content)
            keywords = meta.get("keywords") or []
            if not skill_matches(user_input, skill_folder.name, keywords):
                continue
            display = meta.get("name") or skill_folder.name
            active_skills.append(f"### 【Active Skill: {display}】\n" + (body or content))
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_folder.name}: {e}")

    if not active_skills:
        return ""
    return "\n\n# 【アクティブなスキル（動的ロード専門能力）】\n" + "\n\n".join(active_skills)

def load_knowledge_summary() -> str:
    """プロジェクトの過去のバグ解決やルール(KI)をロードして要約を返す"""
    ki_file = BASE_DIR / "data" / "knowledge" / "project_rules.json"
    if not ki_file.exists():
        return ""
    try:
        data = json.loads(ki_file.read_text(encoding="utf-8"))
        items = [f"- **{item['title']}** ({item['category']}): {item['summary']}" for item in data]
        return "\n\n# 【知識永続化 (Knowledge Items / プロジェクト教訓)】\n以下の過去の解決知見を必ず遵守すること：\n" + "\n".join(items)
    except Exception as e:
        logger.warning(f"Failed to load KI: {e}")
        return ""


