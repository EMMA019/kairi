import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.github_sync import (
    GitHubPushError,
    collect_text_files,
    push_files,
    resolve_repo_spec,
    suggest_repo_name,
)


class _Resp:
    def __init__(self, status_code, json_data=None, text="", content=b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or ""
        self.content = content if content else (self.text.encode("utf-8") if text else b"")

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
        if url.endswith("/user"):
            return _Resp(200, {"login": "me"})
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


class _CreateClient:
    """Missing repo → POST /user/repos (auto_init) → commit on default branch."""

    def __init__(self, *args, **kwargs):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.created = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        self.calls.append(("GET", url, None))
        if url.endswith("/user"):
            return _Resp(200, {"login": "emma"})
        if url.endswith("/repos/emma/kairi-workspace"):
            if self.created:
                return _Resp(200, {"default_branch": "main"})
            return _Resp(404, text="Not Found")
        if "git/ref/heads/main" in url:
            return _Resp(200, {"object": {"sha": "parent1"}})
        if "git/commits/parent1" in url:
            return _Resp(200, {"tree": {"sha": "oldtree"}})
        return _Resp(500, text=url)

    async def post(self, url, json=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/user/repos"):
            assert json["name"] == "kairi-workspace"
            assert json["auto_init"] is True
            assert json["private"] is False
            self.created = True
            return _Resp(201, {"html_url": "https://github.com/emma/kairi-workspace"})
        if url.endswith("/git/trees"):
            assert json.get("base_tree") == "oldtree"
            return _Resp(201, {"sha": "tree1"})
        if url.endswith("/git/commits"):
            assert json.get("parents") == ["parent1"]
            return _Resp(201, {"sha": "commit1"})
        return _Resp(500, text=url)

    async def patch(self, url, json=None):
        self.calls.append(("PATCH", url, json))
        if "git/refs/heads/main" in url:
            return _Resp(200, {"object": {"sha": json["sha"]}})
        return _Resp(500, text=url)


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


def test_suggest_repo_name():
    assert suggest_repo_name("My Site!") == "My-Site"
    assert suggest_repo_name("kairi") == "kairi-workspace"
    assert suggest_repo_name("output") == "kairi-workspace"
    assert suggest_repo_name("workspace") == "kairi-workspace"
    assert suggest_repo_name("") == "kairi-workspace"


def test_resolve_repo_spec():
    assert resolve_repo_spec("", "emma", "output") == "emma/kairi-workspace"
    assert resolve_repo_spec("promo-hp", "emma") == "emma/promo-hp"
    assert resolve_repo_spec("acme/site", "emma") == "acme/site"
    with pytest.raises(GitHubPushError, match="product repo"):
        resolve_repo_spec("kairi", "emma")
    with pytest.raises(GitHubPushError, match="invalid"):
        resolve_repo_spec("emma/no spaces", "emma")


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
    assert result["repo_created"] is False


def test_push_creates_missing_repo():
    client = _CreateClient()

    def _factory(*args, **kwargs):
        return client

    with patch("app.core.github_sync.httpx.AsyncClient", _factory):
        result = asyncio.run(
            push_files(
                [("README.md", "# hi")],
                token="t",
                repo="",
                branch="main",
                message="snap",
                create_if_missing=True,
                workspace_name="output",
            )
        )
    assert result["ok"] is True
    assert result["repo"] == "emma/kairi-workspace"
    assert result["repo_created"] is True
    assert result["html_url"] == "https://github.com/emma/kairi-workspace"
    posts = [c for c in client.calls if c[0] == "POST"]
    assert any(url.endswith("/user/repos") for _, url, _ in posts)


def test_push_rejects_empty_repo_without_create():
    async def _run():
        try:
            await push_files(
                [("a.ts", "x")],
                token="t",
                repo="",
                branch="main",
                message="m",
                create_if_missing=False,
            )
        except GitHubPushError as e:
            return str(e)
        return None

    err = asyncio.run(_run())
    assert err and "create-if-missing" in err


def test_schedule_skips_without_token(monkeypatch):
    monkeypatch.setenv("KAIRI_TEST_GITHUB_PUSH", "1")
    from app.core.github_sync import cancel_scheduled_push, schedule_github_push

    with patch(
        "app.core.github_sync.github_target",
        return_value={
            "token": "",
            "repo": "",
            "branch": "main",
            "create": True,
            "private": False,
            "auto": True,
        },
    ):
        assert schedule_github_push("test") is False
    cancel_scheduled_push()


def test_schedule_skips_when_auto_off(monkeypatch):
    monkeypatch.setenv("KAIRI_TEST_GITHUB_PUSH", "1")
    from app.core.github_sync import cancel_scheduled_push, schedule_github_push

    with patch(
        "app.core.github_sync.github_target",
        return_value={
            "token": "t",
            "repo": "me/site",
            "branch": "main",
            "create": True,
            "private": False,
            "auto": False,
        },
    ):
        assert schedule_github_push("test") is False
    cancel_scheduled_push()


def test_pull_workspace_from_zipball(tmp_path: Path, monkeypatch):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("emma-kairi-workspace-abc/src/App.tsx", "export default function App() {}")
        zf.writestr("emma-kairi-workspace-abc/node_modules/x.js", "skip")
        zf.writestr("emma-kairi-workspace-abc/shot.png", b"\x89PNG")
    zip_bytes = buf.getvalue()

    class _ZipClient(_FakeClient):
        async def get(self, url):
            self.calls.append(("GET", url))
            if url.endswith("/user"):
                return _Resp(200, {"login": "emma"})
            if "zipball" in url:
                return _Resp(200, content=zip_bytes)
            return _Resp(500, text=url)

    monkeypatch.setenv("KAIRI_WORKSPACE_GITHUB_REPO", "emma/kairi-workspace")
    dest = tmp_path / "ws"
    with patch("app.core.github_sync.github_target", return_value={
        "token": "t",
        "repo": "emma/kairi-workspace",
        "branch": "main",
        "create": True,
        "private": False,
        "auto": True,
    }), patch("app.core.github_sync.httpx.AsyncClient", _ZipClient):
        from app.core.github_sync import pull_workspace_into

        result = asyncio.run(pull_workspace_into(dest))
    assert result["file_count"] == 1
    assert (dest / "src" / "App.tsx").read_text(encoding="utf-8") == "export default function App() {}"
    assert not (dest / "node_modules").exists()
