import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager

DB_PATH = Path(__file__).parent.parent.parent / "storage" / "conversations.db"

@asynccontextmanager
async def get_db():
    """データベース接続をコンテキストマネージャーとして取得"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    """データベーススキーマを初期化"""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT REFERENCES sessions(id),
                role TEXT CHECK(role IN ('user', 'assistant')),
                content TEXT,
                raw_response TEXT,
                thinking_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session 
            ON messages(session_id, created_at)
        """)
        
        # フェーズ3: カラムの追加（マイグレーション）
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT")
        except aiosqlite.OperationalError:
            pass # 既にある場合は無視
            
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN search_sources TEXT")
        except aiosqlite.OperationalError:
            pass # 既にある場合は無視

        await db.commit()
