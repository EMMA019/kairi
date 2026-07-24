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
    """ユーザー入力のキーワードに基づいて適切なスキルファイルを動的にロードする"""
    skills_dir = BASE_DIR / "skills"
    if not skills_dir.exists():
        return ""
    
    active_skills = []
    lower_input = (user_input or "").lower()
    
    for skill_folder in skills_dir.iterdir():
        if skill_folder.is_dir():
            skill_file = skill_folder / "SKILL.md"
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    # フォルダ名や主要開発キーワードとの一致を判定
                    keywords = [
                        skill_folder.name, "ui", "react", "python", "backend", "db",
                        "開発", "バグ", "コード", "実装", "修正", "ゲーム", "game",
                        "web", "モダン", "アプリ", "ホビー", "作れ", "作成", "ポーカー",
                        "css", "デザイン", "プログラミング", "リファクタ", "ツール", "システム"
                    ]
                    if skill_folder.name in lower_input or any(kw in lower_input for kw in keywords):
                        active_skills.append(f"### 【Active Skill: {skill_folder.name}】\n" + content)
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


