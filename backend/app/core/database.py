import os
import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "storage" / "conversations.db"


class LibSQLCursorWrapper:
    def __init__(self, result):
        self.rows = result.rows if hasattr(result, "rows") else []

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None


class LibSQLConnectionWrapper:
    def __init__(self, client):
        self.client = client

    async def execute(self, sql: str, params=()):
        if isinstance(params, tuple):
            params = list(params)
        result = await self.client.execute(sql, params)
        return LibSQLCursorWrapper(result)

    async def commit(self):
        pass

    async def close(self):
        await self.client.close()


@asynccontextmanager
async def get_db():
    """データベース接続をコンテキストマネージャーとして取得（TursoクラウドDBまたはローカルSQLite）"""
    turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    turso_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

    if turso_url and turso_url.startswith("libsql://"):
        try:
            import libsql_client
            client = libsql_client.create_client(url=turso_url, auth_token=turso_token or None)
            wrapper = LibSQLConnectionWrapper(client)
            try:
                yield wrapper
            finally:
                await wrapper.close()
            return
        except Exception as e:
            logger.warning(f"TursoクラウドDB接続に失敗しました。ローカルSQLiteを使用します: {e}")

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
        
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN reasoning TEXT")
        except Exception:
            pass
            
        try:
            await db.execute("ALTER TABLE messages ADD COLUMN search_sources TEXT")
        except Exception:
            pass

        await db.commit()

