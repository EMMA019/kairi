"""Export zip + version constant."""
import asyncio
import io
import json
import zipfile
from pathlib import Path

from app.core.app_version import APP_VERSION
from app.routers import export as export_mod
from app.routers.settings import app_settings


def test_app_version_semver_like():
    parts = APP_VERSION.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts[:2])


def test_export_masks_secrets(tmp_path: Path, monkeypatch):
    db = tmp_path / "conversations.db"
    db.write_bytes(b"sqlite-fake")
    monkeypatch.setattr(export_mod, "_STORAGE", tmp_path)
    monkeypatch.setattr(export_mod, "_DB_PATH", db)
    monkeypatch.setattr(
        app_settings,
        "get",
        lambda: {"deepseek_api_key": "sk-secret", "locale": "en"},
    )

    async def _run():
        resp = await export_mod.export_backup(include_secrets=False)
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else bytes(chunk))
        return b"".join(chunks)

    body = asyncio.run(_run())
    zf = zipfile.ZipFile(io.BytesIO(body))
    assert "conversations.db" in zf.namelist()
    data = json.loads(zf.read("settings.json").decode("utf-8"))
    assert data["deepseek_api_key"] == "********"
    assert APP_VERSION in zf.read("VERSION.txt").decode("utf-8")


def test_export_get_rejects_include_secrets_query():
    import pytest
    from fastapi import HTTPException

    async def _run():
        with pytest.raises(HTTPException) as ei:
            await export_mod.export_backup(include_secrets=True)
        assert ei.value.status_code == 400
        assert "with-secrets" in ei.value.detail

    asyncio.run(_run())


def test_export_with_secrets_requires_confirm(tmp_path: Path, monkeypatch):
    import pytest
    from fastapi import HTTPException

    db = tmp_path / "conversations.db"
    db.write_bytes(b"sqlite-fake")
    monkeypatch.setattr(export_mod, "_STORAGE", tmp_path)
    monkeypatch.setattr(export_mod, "_DB_PATH", db)
    monkeypatch.setattr(
        app_settings,
        "get",
        lambda: {"deepseek_api_key": "sk-secret", "locale": "en"},
    )

    async def _deny():
        with pytest.raises(HTTPException) as ei:
            await export_mod.export_backup_with_secrets(
                export_mod.ExportSecretsRequest(confirm_export_secrets=False)
            )
        assert ei.value.status_code == 400

    async def _allow():
        resp = await export_mod.export_backup_with_secrets(
            export_mod.ExportSecretsRequest(confirm_export_secrets=True)
        )
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else bytes(chunk))
        return b"".join(chunks)

    asyncio.run(_deny())
    body = asyncio.run(_allow())
    data = json.loads(zipfile.ZipFile(io.BytesIO(body)).read("settings.json").decode("utf-8"))
    assert data["deepseek_api_key"] == "sk-secret"
