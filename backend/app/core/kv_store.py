"""
KVメモリ管理モジュール。
demo.py の mock_kv_store + filter_kv_by_scope() + format_kv_for_prompt() を移植。
JSON ファイルで永続化。
"""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ベクトル検索はユーザー要望により廃止（関連性が薄い記憶が意図せず引っ張られるのを防ぐため）

STORAGE_PATH = Path(__file__).parent.parent.parent / "storage" / "kv_store.json"

# demo.py から移植したデフォルトKVデータ（10件）
_DEFAULT_KV_DATA = [
    {"id": 1, "category": "preference", "quote": "コーヒーはブラック派かな", "summary": {"target": "コーヒー", "stance": "好き", "tags": ["飲み物", "カフェ", "ブラック", "珈琲"]}},
    {"id": 2, "category": "preference", "quote": "辛いものはあんまり得意じゃない", "summary": {"target": "辛い食べ物", "stance": "苦手", "tags": ["辛い", "スパイス", "唐辛子", "激辛", "料理"]}},
    {"id": 3, "category": "profile", "quote": "猫を2匹飼ってる", "summary": {"target": "猫", "stance": "好き", "tags": ["ペット", "動物", "ねこ", "にゃんこ"]}},
    {"id": 4, "category": "preference", "quote": "ロックよりジャズが好き", "summary": {"target": "ジャズ", "stance": "好き", "tags": ["音楽", "ジャズ", "ロック", "楽器", "演奏"]}},
    {"id": 5, "category": "agreement", "quote": "毎週金曜は早めに切り上げたい", "summary": {"target": "金曜の早退", "stance": "条件付き", "tags": ["金曜", "早退", "仕事", "勤務時間"]}},
    {"id": 6, "category": "preference", "quote": "登山はきついから苦手", "summary": {"target": "登山", "stance": "苦手", "tags": ["山", "アウトドア", "ハイキング", "運動"]}},
    {"id": 7, "category": "profile", "quote": "在宅勤務がメイン", "summary": {"target": "在宅勤務", "stance": "好き", "tags": ["リモートワーク", "テレワーク", "仕事", "自宅"]}},
    {"id": 8, "category": "preference", "quote": "映画は静かなドラマ系が好み", "summary": {"target": "静かなドラマ映画", "stance": "好き", "tags": ["映画", "ドラマ", "映画鑑賞", "DVD", "Netflix"]}},
    {"id": 9, "category": "preference", "quote": "甘いお酒は苦手、辛口が好き", "summary": {"target": "辛口のお酒", "stance": "好き", "tags": ["お酒", "酒", "辛口", "ワイン", "日本酒", "ビール", "飲み会"]}},
    {"id": 10, "category": "agreement", "quote": "誕生日は特に祝わなくていい", "summary": {"target": "誕生日祝い", "stance": "条件付き", "tags": ["誕生日", "お祝い", "プレゼント", "記念日"]}},
]


class KVStore:
    """KVメモリの管理（CRUD + フィルタリング + JSON永続化）"""

    def __init__(self):
        self._store: list[dict] = []
        self._next_id: int = 1
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        """ストレージからKVデータをロード。存在しなければデフォルトデータで初期化。"""
        if STORAGE_PATH.exists():
            try:
                with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                    self._store = json.load(f)
                if self._store:
                    self._next_id = max(e.get("id", 0) for e in self._store) + 1
                logger.info(f"KVストアをロードしました: {len(self._store)}件")
            except (json.JSONDecodeError, Exception) as e:
                logger.info(f"KVストアのロードに失敗、デフォルトデータを使用: {e}")
                self._init_defaults()
        else:
            self._init_defaults()

    def _init_defaults(self):
        """デフォルトKVデータで初期化"""
        self._store = [entry.copy() for entry in _DEFAULT_KV_DATA]
        self._next_id = 11
        self._save()

    def _save(self):
        """現在のストアをJSONファイルにアトミック保存（書き込み途中のクラッシュ耐性）"""
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(STORAGE_PATH.parent), suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._store, f, ensure_ascii=False, indent=2)
            
            try:
                os.replace(tmp_path, str(STORAGE_PATH))
            except PermissionError:
                # Windows環境下等でファイルロック(Uvicornリロード監視等)によりos.replaceが失敗する場合のフォールバック
                logger.warning("os.replace failed with PermissionError. Falling back to direct write.")
                with open(STORAGE_PATH, "w", encoding="utf-8") as fallback_f:
                    json.dump(self._store, fallback_f, ensure_ascii=False, indent=2)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"KVストア保存エラー: {e}")
            # 一時ファイルが残っていたら掃除
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def get_all(self) -> list[dict]:
        """全KVエントリを取得（ファイルが更新されていれば自動再ロード）"""
        with self._lock:
            self._load()
            return self._store

    def get_by_category(self, category: str) -> list[dict]:
        """指定カテゴリのKVエントリを取得"""
        return [e for e in self._store if e.get("category") == category]

    # ============================================================
    # 新規追加：set / get（スキャン結果など一時データ用）
    # ============================================================
    def set(self, key: str, value: str) -> None:
        """任意のキーで文字列データを保存（スキャン結果など一時データ用）"""
        with self._lock:
            # 既存のエントリを検索（キーを target として利用）
            for entry in self._store:
                if entry["summary"].get("target") == key:
                    entry["summary"]["note"] = value
                    self._save()
                    return
            # 新規追加
            new_entry = {
                "id": self._next_id,
                "category": "profile",
                "quote": key,
                "summary": {
                    "target": key,
                    "note": value,
                    "tags": ["一時データ", "スキャン結果"]
                }
            }
            self._next_id += 1
            self._store.append(new_entry)
            self._save()

    def get(self, key: str) -> str | None:
        """任意のキーで保存されたデータを取得"""
        with self._lock:
            for entry in self._store:
                if entry["summary"].get("target") == key:
                    return entry["summary"].get("note")
            return None
    # ============================================================

    def add(self, entry: dict) -> dict:
        """新規KVエントリを追加"""
        with self._lock:
            self._load()
            entry["id"] = self._next_id
            self._next_id += 1
            self._store.append(entry)
            self._save()
        logger.info(f"KV追加: {entry.get('summary', {}).get('target', 'unknown')}")
        return entry

    def delete(self, entry_id: int) -> bool:
        """指定IDのKVエントリを削除"""
        with self._lock:
            self._load()
            before = len(self._store)
            self._store = [e for e in self._store if e.get("id") != entry_id]
            if len(self._store) < before:
                self._save()
                logger.info(f"KV削除: id={entry_id}")
                return True
        return False

    def update(self, entry_id: int, entry: dict) -> Optional[dict]:
        """指定IDのKVエントリを更新"""
        with self._lock:
            self._load()
            for i, e in enumerate(self._store):
                if e.get("id") == entry_id:
                    # 部分更新: 指定されたフィールドのみ上書き
                    if "quote" in entry and entry["quote"] is not None:
                        e["quote"] = entry["quote"]
                    if "summary" in entry and entry["summary"] is not None:
                        # summary内も部分更新
                        for key, val in entry["summary"].items():
                            if val is not None:
                                e["summary"][key] = val
                    if "category" in entry and entry["category"] is not None:
                        e["category"] = entry["category"]
                    
                    # 埋め込み再計算は廃止
                    self._save()
                    logger.info(f"KV更新: id={entry_id}")
                    return e
        return None

    def get_exclusions(self) -> list[str]:
        """除外対象のキーワード一覧を取得"""
        exclusions = []
        for e in self._store:
            if e.get("category") == "exclusion":
                exclusions.append(e["summary"]["target"])
                # tagsも除外対象に含める
                exclusions.extend(e["summary"].get("tags", []))
        return exclusions

    def filter_by_scope(self, user_input: str, top_k: int = 25) -> list[dict]:
        """
        重要カテゴリー（project / profile / rule / preference / schedule）は常にコンテキストに常駐させる。
        その他のエントリもキーワード検索で合致すれば追加する。
        """
        with self._lock:
            self._load()
            candidates = [e for e in self._store if e.get("category") != "exclusion"]
        if not candidates:
            return []

        always_inject = []
        keyword_matched = []
        user_lower = user_input.lower()

        for entry in candidates:
            cat = entry.get("category", "")
            # プロジェクト約束やプロフィール、好み、予定、開発ルール等の重要記憶は常に注入する
            if cat in ("project", "profile", "rule", "preference", "schedule"):
                always_inject.append(entry)
                continue

            target = entry.get("summary", {}).get("target", "")
            tags = entry.get("summary", {}).get("tags", [])
            quote = entry.get("quote", "")
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

    def format_summary(self) -> str:
        """全KVメモリの一覧をプロンプト注入用テキストに整形（AIが自分の記憶状態を把握するため）"""
        if not self._store:
            return "（KVメモリは空です）"
        lines = []
        for kv in self._store:
            cat = kv.get("category", "")
            target = kv["summary"]["target"]
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