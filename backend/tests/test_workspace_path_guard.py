"""P0: workspace path must not escape via Windows drive-absolute paths."""
from pathlib import Path

import pytest

from app.core.sandbox import normalize_safe_path, resolve_workspace_target


def test_drive_absolute_path_stays_inside_workspace(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    # Historic bug: Path(ws) / "C:/Windows/Temp/evil.txt" → C:\Windows\Temp\evil.txt
    naive = (ws / "C:/Windows/Temp/evil.txt").resolve()
    assert "windows" in str(naive).lower() and str(ws.resolve()).lower() not in str(naive).lower()

    target = resolve_workspace_target(ws, "C:/Windows/Temp/evil.txt")
    # Must remain under workspace — never the real C:\Windows\Temp\...
    target.relative_to(ws.resolve())
    assert target != Path(r"C:\Windows\Temp\evil.txt").resolve()
    assert str(target).lower().startswith(str(ws.resolve()).lower())


def test_parent_traversal_cannot_escape(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    target = resolve_workspace_target(ws, "../../secret.txt")
    # After sanitize, should land inside ws (basename or emptied segments)
    assert str(ws.resolve()) in str(target)
    try:
        target.relative_to(ws.resolve())
    except ValueError:
        pytest.fail("escaped workspace")


def test_normalize_strips_drive_prefix(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    safe = normalize_safe_path(str(ws), r"D:\other\file.py")
    assert ":" not in safe
    assert "file.py" in safe


def test_resolve_rejects_symlink_escape(tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pwn.txt").write_text("x", encoding="utf-8")
    link = ws / "linkdir"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not permitted on this host")
    # Path resolves through the symlink to outside/ — must raise
    with pytest.raises(ValueError):
        resolve_workspace_target(ws, "linkdir/pwn.txt")
