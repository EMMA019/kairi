import asyncio
from pathlib import Path
from unittest.mock import patch

from app.core.github_sync import GitHubPushError, collect_text_files, push_files


class _Resp:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or ""

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        self.calls.append(("GET", url))
        if url.endswith("/repos/me/site"):
            return _Resp(200, {"default_branch": "main"})
        if "git/ref/heads/main" in url:
            return _Resp(404)
        return _Resp(500, text=url)

    async def post(self, url, json=None):
        self.calls.append(("POST", url))
        if url.endswith("/git/trees"):
            assert json and json["tree"][0]["path"] == "README.md"
            return _Resp(201, {"sha": "tree1"})
        if url.endswith("/git/commits"):
            return _Resp(201, {"sha": "commit1"})
        if url.endswith("/git/refs"):
            return _Resp(201, {"ref": "refs/heads/main"})
        return _Resp(500, text=url)

    async def patch(self, url, json=None):
        return _Resp(500, text="unexpected patch")


def test_collect_skips_ignored_and_binary(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export default function App() {}", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("nope", encoding="utf-8")
    (tmp_path / "shot.png").write_bytes(b"\x89PNG")
    files = collect_text_files(
        tmp_path,
        ignore_dirs={"node_modules", ".git"},
        ignore_exts={".png", ".jpg"},
    )
    paths = [p for p, _ in files]
    assert paths == ["src/App.tsx"]


def test_push_files_creates_commit():
    with patch("app.core.github_sync.httpx.AsyncClient", _FakeClient):
        result = asyncio.run(
            push_files(
                [("README.md", "# hi")],
                token="t",
                repo="me/site",
                branch="main",
                message="snap",
            )
        )
    assert result["ok"] is True
    assert result["sha"] == "commit1"
    assert result["file_count"] == 1
    assert result["url"].endswith("/commit/commit1")


def test_push_rejects_empty_repo():
    async def _run():
        try:
            await push_files([("a.ts", "x")], token="t", repo="", branch="main", message="m")
        except GitHubPushError as e:
            return str(e)
        return None

    err = asyncio.run(_run())
    assert err and "owner/name" in err
