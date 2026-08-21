import asyncio
from pathlib import Path

from app.core import database as dbmod
from app.core import workspace_store as store


def test_upsert_hydrate_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KAIRI_TEST_WORKSPACE_STORE", "1")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "conversations.db")
    ws = tmp_path / "workspace"
    ws.mkdir()

    async def _run():
        await store.init_workspace_store()
        await store.upsert_file("src/App.tsx", "export const n = 1\n")
        await store.upsert_file("README.md", "# hi\n")
        alive = await store.list_alive()
        assert [p for p, _ in alive] == ["README.md", "src/App.tsx"]
        n = await store.hydrate_disk(ws)
        assert n == 2
        assert (ws / "src" / "App.tsx").read_text(encoding="utf-8") == "export const n = 1\n"
        # non-empty disk is left alone
        (ws / "README.md").write_text("local\n", encoding="utf-8")
        assert await store.hydrate_disk(ws) == 0
        assert (ws / "README.md").read_text(encoding="utf-8") == "local\n"

    asyncio.run(_run())


def test_snapshot_disk_to_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KAIRI_TEST_WORKSPACE_STORE", "1")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "conversations.db")
    ws = tmp_path / "workspace"
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "a.ts").write_text("export const a = 1\n", encoding="utf-8")
    (ws / "gone.ts").write_text("bye\n", encoding="utf-8")

    async def _run():
        await store.init_workspace_store()
        await store.upsert_file("gone.ts", "bye\n")
        (ws / "gone.ts").unlink()
        n = await store.snapshot_disk_to_db(ws)
        assert n == 1
        alive = dict(await store.list_alive())
        assert "src/a.ts" in alive
        assert "gone.ts" not in alive

    asyncio.run(_run())


def test_cloud_backend_turso(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example")
    assert store.cloud_backend() == "turso"
    monkeypatch.delenv("TURSO_DATABASE_URL")
    assert store.cloud_backend() == "local-db"
