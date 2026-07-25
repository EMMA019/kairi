"""
KVメモリ管理モジュール。
demo.py の mock_kv_store + filter_kv_by_scope() + format_kv_for_prompt() を移植。
JSON ファイルで永続化。
"""
import json
from typing import Optional
from app.utils.logger import get_logger
from app.core.database import get_db

logger = get_logger(__name__)

# demo.py から移植したデフォルトKVデータ（10件）
_DEFAULT_KV_DATA = [
    {"category": "preference", "quote": "コーヒーはブラック派かな", "summary": {"target": "コーヒー", "stance": "好き", "tags": ["飲み物", "カフェ", "ブラック", "珈琲"]}},
    {"category": "preference", "quote": "辛いものはあんまり得意じゃない", "summary": {"target": "辛い食べ物", "stance": "苦手", "tags": ["辛い", "スパイス", "唐辛子", "激辛", "料理"]}},
    {"category": "profile", "quote": "猫を2匹飼ってる", "summary": {"target": "猫", "stance": "好き", "tags": ["ペット", "動物", "ねこ", "にゃんこ"]}},
    {"category": "preference", "quote": "ロックよりジャズが好き", "summary": {"target": "ジャズ", "stance": "好き", "tags": ["音楽", "ジャズ", "ロック", "楽器", "演奏"]}},
    {"category": "agreement", "quote": "毎週金曜は早めに切り上げたい", "summary": {"target": "金曜の早退", "stance": "条件付き", "tags": ["金曜", "早退", "仕事", "勤務時間"]}},
    {"category": "preference", "quote": "登山はきついから苦手", "summary": {"target": "登山", "stance": "苦手", "tags": ["山", "アウトドア", "ハイキング", "運動"]}},
    {"category": "profile", "quote": "在宅勤務がメイン", "summary": {"target": "在宅勤務", "stance": "好き", "tags": ["リモートワーク", "テレワーク", "仕事", "自宅"]}},
    {"category": "preference", "quote": "映画は静かなドラマ系が好み", "summary": {"target": "静かなドラマ映画", "stance": "好き", "tags": ["映画", "ドラマ", "映画鑑賞", "DVD", "Netflix"]}},
    {"category": "preference", "quote": "甘いお酒は苦手、辛口が好き", "summary": {"target": "辛口のお酒", "stance": "好き", "tags": ["お酒", "酒", "辛口", "ワイン", "日本酒", "ビール", "飲み会"]}},
    {"category": "agreement", "quote": "誕生日は特に祝わなくていい", "summary": {"target": "誕生日祝い", "stance": "条件付き", "tags": ["誕生日", "お祝い", "プレゼント", "記念日"]}},
]

class KVStore:
    """KVメモリの管理（CRUD + フィルタリング + Turso/SQLite永続化）"""

    def __init__(self):
        pass

    async def _init_defaults_if_empty(self):
        """データベースが空の場合、デフォルトデータを挿入する"""
        async with get_db() as db:
            result = await db.execute("SELECT COUNT(id) FROM kv_memories")
            row = await result.fetchone()
            count = row[0] if row else 0
            if count == 0:
                for entry in _DEFAULT_KV_DATA:
                    await self._insert_to_db(db, entry)
                await db.commit()
                logger.info("KVメモリのデフォルトデータをデータベースに挿入しました。")

    async def _insert_to_db(self, db, entry: dict):
        summary = entry.get("summary", {})
        tags = summary.get("tags", [])
        await db.execute(
            """
            INSERT INTO kv_memories (category, quote, target, stance, note, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("category"),
                entry.get("quote"),
                summary.get("target"),
                summary.get("stance"),
                summary.get("note"),
                json.dumps(tags, ensure_ascii=False) if tags else "[]"
            )
        )

    def _row_to_dict(self, row) -> dict:
        # id: 0, category: 1, quote: 2, target: 3, stance: 4, note: 5, tags: 6
        tags_str = row[6]
        tags = json.loads(tags_str) if tags_str else []
        return {
            "id": row[0],
            "category": row[1],
            "quote": row[2],
            "summary": {
                "target": row[3],
                "stance": row[4],
                "note": row[5],
                "tags": tags
            }
        }

    async def get_all(self) -> list[dict]:
        """全KVエントリを取得"""
        await self._init_defaults_if_empty()
        async with get_db() as db:
            result = await db.execute("SELECT id, category, quote, target, stance, note, tags FROM kv_memories ORDER BY id ASC")
            rows = await result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_by_category(self, category: str) -> list[dict]:
        """指定カテゴリのKVエントリを取得"""
        await self._init_defaults_if_empty()
        async with get_db() as db:
            result = await db.execute("SELECT id, category, quote, target, stance, note, tags FROM kv_memories WHERE category = ? ORDER BY id ASC", (category,))
            rows = await result.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def set(self, key: str, value: str) -> None:
        """任意のキーで文字列データを保存（スキャン結果など一時データ用）"""
        await self._init_defaults_if_empty()
        async with get_db() as db:
            result = await db.execute("SELECT id, category, quote, target, stance, note, tags FROM kv_memories WHERE target = ?", (key,))
            row = await result.fetchone()
            if row:
                await db.execute(
                    "UPDATE kv_memories SET note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (value, row[0])
                )
            else:
                tags = json.dumps(["一時データ", "スキャン結果"], ensure_ascii=False)
                await db.execute(
                    """
                    INSERT INTO kv_memories (category, quote, target, stance, note, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("profile", key, key, None, value, tags)
                )
            await db.commit()

    async def get(self, key: str) -> str | None:
        """任意のキーで保存されたデータを取得"""
        await self._init_defaults_if_empty()
        async with get_db() as db:
            result = await db.execute("SELECT note FROM kv_memories WHERE target = ?", (key,))
            row = await result.fetchone()
            if row:
                return row[0]
            return None

    async def add(self, entry: dict) -> dict:
        """新規KVエントリを追加"""
        await self._init_defaults_if_empty()
        async with get_db() as db:
            summary = entry.get("summary", {})
            tags = summary.get("tags", [])
            await db.execute(
                """
                INSERT INTO kv_memories (category, quote, target, stance, note, tags)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.get("category"),
                    entry.get("quote"),
                    summary.get("target"),
                    summary.get("stance"),
                    summary.get("note"),
                    json.dumps(tags, ensure_ascii=False) if tags else "[]"
                )
            )
            # 挿入した行のIDを取得
            result = await db.execute("SELECT last_insert_rowid()")
            row = await result.fetchone()
            new_id = row[0] if row else None
            
            await db.commit()
            
            entry["id"] = new_id
            logger.info(f"KV追加: {summary.get('target', 'unknown')}")
            return entry

    async def delete(self, entry_id: int) -> bool:
        """指定IDのKVエントリを削除"""
        async with get_db() as db:
            result = await db.execute("SELECT id FROM kv_memories WHERE id = ?", (entry_id,))
            if not await result.fetchone():
                return False
            await db.execute("DELETE FROM kv_memories WHERE id = ?", (entry_id,))
            await db.commit()
            logger.info(f"KV削除: id={entry_id}")
            return True

    async def update(self, entry_id: int, entry: dict) -> Optional[dict]:
        """指定IDのKVエントリを更新"""
        async with get_db() as db:
            result = await db.execute("SELECT id, category, quote, target, stance, note, tags FROM kv_memories WHERE id = ?", (entry_id,))
            row = await result.fetchone()
            if not row:
                return None
                
            current = self._row_to_dict(row)
            
            # 部分更新
            if "quote" in entry and entry["quote"] is not None:
                current["quote"] = entry["quote"]
            if "summary" in entry and entry["summary"] is not None:
                for key, val in entry["summary"].items():
                    if val is not None:
                        current["summary"][key] = val
            if "category" in entry and entry["category"] is not None:
                current["category"] = entry["category"]
                
            tags = current["summary"].get("tags", [])
            await db.execute(
                """
                UPDATE kv_memories 
                SET category = ?, quote = ?, target = ?, stance = ?, note = ?, tags = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    current["category"],
                    current["quote"],
                    current["summary"].get("target"),
                    current["summary"].get("stance"),
                    current["summary"].get("note"),
                    json.dumps(tags, ensure_ascii=False) if tags else "[]",
                    entry_id
                )
            )
            await db.commit()
            logger.info(f"KV更新: id={entry_id}")
            return current

    async def get_exclusions(self) -> list[str]:
        """除外対象のキーワード一覧を取得"""
        exclusions = []
        async with get_db() as db:
            result = await db.execute("SELECT target, tags FROM kv_memories WHERE category = 'exclusion'")
            rows = await result.fetchall()
            for row in rows:
                exclusions.append(row[0])
                tags_str = row[1]
                tags = json.loads(tags_str) if tags_str else []
                exclusions.extend(tags)
        return exclusions

    async def filter_by_scope(self, user_input: str, top_k: int = 25) -> list[dict]:
        """
        重要カテゴリー（project / profile / rule / preference / schedule）は常にコンテキストに常駐させる。
        その他のエントリもキーワード検索で合致すれば追加する。
        """
        all_memories = await self.get_all()
        candidates = [e for e in all_memories if e.get("category") != "exclusion"]
        
        if not candidates:
            return []

        always_inject = []
        keyword_matched = []
        user_lower = user_input.lower()

        for entry in candidates:
            cat = entry.get("category", "")
            if cat in ("project", "profile", "rule", "preference", "schedule"):
                always_inject.append(entry)
                continue

            target = entry.get("summary", {}).get("target", "")
            tags = entry.get("summary", {}).get("tags", [])
            
            if (
                target in user_input
                or any(tag in user_lower for tag in tags if len(tag) >= 2)
                or any(tok in user_input for tok in target.split() if len(tok) >= 2)
                or any(kw in user_input for kw in ["アプリ", "プロジェクト", "作る", "覚えて", "約束", "タスク", "好き", "予定", "旅行"])
            ):
                keyword_matched.append(entry)

        combined = always_inject + [e for e in keyword_matched if e not in always_inject]
        return combined[:top_k]

    def format_for_prompt(self, kv_list: list[dict]) -> str:
        """KVリストをプロンプト注入用テキストに整形"""
        if not kv_list:
            return "（現在保存されている長期記憶・プロジェクトはありません）"
        lines = ["【ユーザーの長期記憶・合意プロジェクト一覧】"]
        for kv in kv_list:
            cat = kv.get("category", "info")
            target = kv["summary"].get("target", "")
            stance = kv["summary"].get("stance", "")
            note = kv["summary"].get("note", "")
            quote = kv.get("quote", "")
            lines.append(f"- [{cat.upper()}] {target} ({stance}): {note} (引用: 「{quote}」)")
        return "\n".join(lines)

    async def format_summary(self) -> str:
        """全KVメモリの一覧をプロンプト注入用テキストに整形（AIが自分の記憶状態を把握するため）"""
        all_memories = await self.get_all()
        if not all_memories:
            return "（KVメモリは空です）"
        lines = []
        for kv in all_memories:
            cat = kv.get("category", "")
            target = kv["summary"].get("target", "")
            stance = kv["summary"].get("stance", "")
            note = kv["summary"].get("note", "")
            tags = kv["summary"].get("tags", [])
            detail = f'stance="{stance}"' if stance else f'note="{note}"'
            tags_str = ", ".join(tags) if tags else ""
            lines.append(
                f'- [ID:{kv["id"]}] category="{cat}", target="{target}", {detail}'
                + (f', tags=[{tags_str}]' if tags_str else '')
            )
        return "\n".join(lines)


# シングルトンインスタンス
kv_store = KVStore()