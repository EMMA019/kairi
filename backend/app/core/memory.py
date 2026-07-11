import json
import re
from typing import Any
from app.core.llm_client import call_model, DEFAULT_DEEPSEEK_CHAT_MODEL
from app.core.kv_store import kv_store
from app.utils.logger import get_logger

logger = get_logger(__name__)

MEMORY_SYSTEM_PROMPT = """あなたは会話からユーザーに関する記憶（メモリ）を自動抽出・更新するバックグラウンドエージェントです。
以下の会話内容を分析し、KVストア（ユーザーのプロフィール、好み、将来のプロジェクト約束、開発ルールなどの記憶）に
追加、更新、または削除すべき情報があるか判定してください。

とくにユーザーが「〜と覚えて」「これからは〜して」「今後のタスクとして〜を覚えておいて」などと明示的に指示した場合は必ず保存してください。
注意: 単なる「OK」「GO」「承認します。実装してください」などの一時的な相槌や承認ステータスは絶対に保存しないでください。

追加すべき記憶がない場合は空の配列 `[]` を出力してください。
出力形式は以下のJSONの配列のみとしてください。それ以外のテキストは一切出力しないでください。

[
  {
    "action": "add" | "update" | "delete",
    "target_id": null,
    "category": "project" | "profile" | "preference" | "rule" | "exclusion",
    "quote": "ユーザー発言からの直接引用",
    "summary": {
      "target": "対象（例：顔写真保護アプリ開発、UIデザインルール等）",
      "stance": "約束" | "好き" | "苦手" | "ルール",
      "note": "具体的な詳細や技術スタック・内容の要約",
      "tags": ["プロジェクト", "約束", "重要"]
    }
  }
]
"""

async def extract_and_save_memory(session_id: str, user_input: str, ai_response: str):
    """
    非同期で会話内容からメモリを抽出し、KVストアを更新する
    """
    # すでに保存されている全メモリ一覧を渡し、重複や上書きを防ぐ
    current_memory = kv_store.format_summary()
    
    prompt = f"【現在のメモリ状態】\n{current_memory}\n\n【今回の会話】\nユーザー: {user_input}\nAI: {ai_response}\n\n"
    prompt += "追加・更新・削除すべきメモリがあれば、JSON配列形式で出力してください。"
    
    try:
        from app.routers.settings import app_settings
        settings = app_settings.get()
        provider = settings.get("planner_provider", "deepseek")
        model_name = settings.get("planner_model", "deepseek-v4-flash")

        response_text = await call_model(
            system_instruction=MEMORY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            model_name=model_name,
            provider=provider,
            max_tokens=1000
        )
        
        # JSONの配列部分を抽出
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            actions = json.loads(json_str)
            
            for action_data in actions:
                action = action_data.get("action")
                if action == "add":
                    kv_store.add(action_data)
                    logger.info(f"自動メモリ抽出: 追加 - {action_data.get('summary', {}).get('target')}")
                elif action == "update" and action_data.get("target_id"):
                    kv_store.update(action_data["target_id"], action_data)
                    logger.info(f"自動メモリ抽出: 更新 - ID {action_data['target_id']}")
                elif action == "delete" and action_data.get("target_id"):
                    kv_store.delete(action_data["target_id"])
                    logger.info(f"自動メモリ抽出: 削除 - ID {action_data['target_id']}")
    except json.JSONDecodeError:
        pass # JSONがない場合は何もしない
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
