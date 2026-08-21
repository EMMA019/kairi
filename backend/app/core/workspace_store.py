"""Durable workspace files — same cloud DB as chat (Turso or local SQLite).

Render's repo `output/` dies on every deploy. Chat survived because it lives in
`conversations.db` / Turso. Workspace files now use that same store. The local
directory is only a working copy for tools and the sandbox.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_FILE_BYTES = 400_000
MAX_FILES = 80


def cloud_backend() -> str:
    if (os.environ.get("TURSO_DATABASE_URL") or "").strip():
        return "turso"
    return "local-db"


def _row_get(row: Any, *keys: str | int) -> Any:
    if row is None:
        return None
    if hasattr(row, "keys"):
        for k in keys:
            if isinstance(k, str) and k in row.keys():
                return row[k]
        return None
    for k in keys:
        if isinstance(k, int):
            try:
                return row[k]
            except (IndexError, TypeError):
                continue
    return None


async def init_workspace_store() -> None:
    from app.core.database import get_db

    async with get_db() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_files (
                path TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                updated_at REAL NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.commit()


async def upsert_file(rel_path: str, content: str) -> None:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        logger.warning(f"workspace cloud skip (too large): {rel}")
        return
    from app.core.database import get_db

    await init_workspace_store()
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO workspace_files (path, content, updated_at, deleted) "
            "VALUES (?, ?, ?, 0)",
            (rel, content, time.time()),
        )
        await db.commit()


async def mark_deleted(rel_path: str) -> None:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel:
        return
    from app.core.database import get_db

    await init_workspace_store()
    async with get_db() as db:
        await db.execute(
            "UPDATE workspace_files SET deleted=1, updated_at=? WHERE path=?",
            (time.time(), rel),
        )
        await db.commit()


async def list_alive() -> list[tuple[str, str]]:
    from app.core.database import get_db

    await init_workspace_store()
    async with get_db() as db:
        cur = await db.execute(
            "SELECT path, content FROM workspace_files WHERE deleted=0 ORDER BY path"
        )
        rows = await cur.fetchall()
    out: list[tuple[str, str]] = []
    for row in rows or []:
        path = str(_row_get(row, "path", 0) or "")
        content = str(_row_get(row, "content", 1) or "")
        if path:
            out.append((path, content))
        if len(out) >= MAX_FILES:
            break
    return out


async def snapshot_disk_to_db(root: Path | None = None) -> int:
    """Replace the cloud snapshot with the current working-copy tree."""
    from app.core.github_sync import collect_text_files
    from app.routers.workspace import IGNORE_DIRS, IGNORE_EXTS, get_workspace_dir

    dest = root or get_workspace_dir()
    files = collect_text_files(dest, ignore_dirs=IGNORE_DIRS, ignore_exts=IGNORE_EXTS)
    from app.core.database import get_db

    await init_workspace_store()
    keep = {p for p, _ in files}
    async with get_db() as db:
        for path, content in files:
            await db.execute(
                "INSERT OR REPLACE INTO workspace_files (path, content, updated_at, deleted) "
                "VALUES (?, ?, ?, 0)",
                (path, content, time.time()),
            )
        cur = await db.execute("SELECT path FROM workspace_files WHERE deleted=0")
        rows = await cur.fetchall()
        for row in rows or []:
            path = str(_row_get(row, "path", 0) or "")
            if path and path not in keep:
                await db.execute(
                    "UPDATE workspace_files SET deleted=1, updated_at=? WHERE path=?",
                    (time.time(), path),
                )
        await db.commit()
    return len(files)


async def hydrate_disk(root: Path | None = None) -> int:
    """If the working copy is empty, restore files from the cloud DB."""
    from app.routers.workspace import IGNORE_DIRS, IGNORE_EXTS, get_workspace_dir
    from app.core.github_sync import collect_text_files

    dest = root or get_workspace_dir()
    dest.mkdir(parents=True, exist_ok=True)
    existing = collect_text_files(dest, ignore_dirs=IGNORE_DIRS, ignore_exts=IGNORE_EXTS)
    if existing:
        return 0
    files = await list_alive()
    if not files:
        return 0
    written = 0
    for rel, content in files:
        target = dest / rel
        if ".." in Path(rel).parts:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written += 1
        except OSError as e:
            logger.warning(f"hydrate skip {rel}: {e}")
    if written:
        logger.info(f"✅ restored {written} workspace files from {cloud_backend()}")
    return written


def _spawn(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.warning(f"workspace cloud persist failed: {e}")
        return
    task = loop.create_task(coro)

    def _done(t: asyncio.Task) -> None:
        try:
            t.result()
        except Exception as e:
            logger.warning(f"workspace cloud persist failed: {e}")

    task.add_done_callback(_done)


def persist_workspace_file(rel_path: str, content: str) -> None:
    """Write-through to the cloud DB, then schedule GitHub. Never raises."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("KAIRI_TEST_WORKSPACE_STORE"):
        return
    _spawn(upsert_file(rel_path, content))
    try:
        from app.core.github_sync import schedule_github_push

        schedule_github_push("write")
    except Exception as e:
        logger.warning(f"github auto-push schedule failed: {e}")


def persist_workspace_delete(rel_path: str) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("KAIRI_TEST_WORKSPACE_STORE"):
        return
    _spawn(mark_deleted(rel_path))
    try:
        from app.core.github_sync import schedule_github_push

        schedule_github_push("delete")
    except Exception as e:
        logger.warning(f"github auto-push schedule failed: {e}")


async def restore_durable_workspace() -> dict[str, Any]:
    """Boot: cloud DB first, then GitHub if the working copy is still empty."""
    from app.routers.workspace import get_workspace_dir

    ws = get_workspace_dir()
    from_db = await hydrate_disk(ws)
    from_gh = 0
    if from_db == 0:
        try:
            from app.core.github_sync import pull_workspace_into

            pulled = await pull_workspace_into(ws)
            from_gh = int(pulled.get("file_count") or 0)
            if from_gh:
                await snapshot_disk_to_db(ws)
        except Exception as e:
            logger.warning(f"github workspace restore skipped: {e}")
    return {
        "ok": True,
        "backend": cloud_backend(),
        "from_db": from_db,
        "from_github": from_gh,
        "root": str(ws),
    }
