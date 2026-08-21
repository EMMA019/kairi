"""Push the local workspace tree to a GitHub repo via the Git Data API.

Render disks are ephemeral — this is how generated files survive a redeploy.
Requires a token with `contents:write` on YOUR repo (create the empty repo first).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_FILES = 80
MAX_FILE_BYTES = 400_000
GITHUB_API = "https://api.github.com"


def _token_and_repo(settings: dict[str, Any] | None = None) -> tuple[str, str, str]:
    s = settings or {}
    try:
        if not s:
            from app.routers.settings import app_settings

            s = app_settings.get() or {}
    except Exception:
        s = s or {}
    token = (
        os.environ.get("KAIRI_WORKSPACE_GITHUB_TOKEN")
        or os.environ.get("KAIRI_PROMO_GITHUB_TOKEN")
        or (s.get("github_token") or "")
    ).strip()
    repo = (
        os.environ.get("KAIRI_WORKSPACE_GITHUB_REPO")
        or (s.get("workspace_github_repo") or "")
        or (s.get("promo_github_repo") or "")
    ).strip().lstrip("/")
    branch = (
        os.environ.get("KAIRI_WORKSPACE_GITHUB_BRANCH")
        or (s.get("workspace_github_branch") or "")
        or "main"
    ).strip() or "main"
    return token, repo, branch


def collect_text_files(
    root: Path,
    *,
    ignore_dirs: Iterable[str],
    ignore_exts: Iterable[str],
    prefix: str = "",
) -> list[tuple[str, str]]:
    """Return (posix_relpath, utf-8 text) pairs under root."""
    ignore_d = set(ignore_dirs)
    ignore_e = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in ignore_exts}
    out: list[tuple[str, str]] = []
    root = root.resolve()
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in ignore_d and not d.startswith(".")
        ]
        for name in sorted(filenames):
            if name.startswith(".") or name == "__pycache__":
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in ignore_e:
                continue
            path = Path(dirpath) / name
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(root).as_posix()
            if prefix:
                rel = f"{prefix.rstrip('/')}/{rel}"
            out.append((rel, text))
            if len(out) >= MAX_FILES:
                return out
    return out


class GitHubPushError(RuntimeError):
    pass


async def push_files(
    files: list[tuple[str, str]],
    *,
    token: str,
    repo: str,
    branch: str,
    message: str,
) -> dict[str, Any]:
    if not token:
        raise GitHubPushError("github_token / KAIRI_WORKSPACE_GITHUB_TOKEN is not set")
    if not repo or "/" not in repo:
        raise GitHubPushError("workspace_github_repo must be owner/name (create the empty repo first)")
    if not files:
        raise GitHubPushError("workspace is empty — nothing to push")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kairi-workspace-sync",
    }
    owner, name = repo.split("/", 1)
    base = f"{GITHUB_API}/repos/{owner}/{name}"

    async with httpx.AsyncClient(timeout=40.0, headers=headers) as client:
        repo_res = await client.get(base)
        if repo_res.status_code == 404:
            raise GitHubPushError(
                f"repo {repo} not found. Create an empty GitHub repo first, then retry."
            )
        if repo_res.status_code >= 400:
            raise GitHubPushError(f"github {repo_res.status_code}: {repo_res.text[:300]}")
        repo_json = repo_res.json()
        default_branch = (repo_json.get("default_branch") or "main").strip()

        parent_sha: str | None = None
        base_tree: str | None = None
        ref_res = await client.get(f"{base}/git/ref/heads/{branch}")
        if ref_res.status_code == 200:
            parent_sha = ((ref_res.json() or {}).get("object") or {}).get("sha")
        elif ref_res.status_code == 404 and branch != default_branch:
            def_res = await client.get(f"{base}/git/ref/heads/{default_branch}")
            if def_res.status_code == 200:
                parent_sha = ((def_res.json() or {}).get("object") or {}).get("sha")
        elif ref_res.status_code not in (200, 404):
            raise GitHubPushError(f"github ref {ref_res.status_code}: {ref_res.text[:300]}")

        if parent_sha:
            commit_res = await client.get(f"{base}/git/commits/{parent_sha}")
            if commit_res.status_code >= 400:
                raise GitHubPushError(f"github commit {commit_res.status_code}: {commit_res.text[:300]}")
            base_tree = ((commit_res.json() or {}).get("tree") or {}).get("sha")

        tree_payload: dict[str, Any] = {
            "tree": [
                {"path": path, "mode": "100644", "type": "blob", "content": content}
                for path, content in files
            ],
        }
        if base_tree:
            tree_payload["base_tree"] = base_tree
        tree_res = await client.post(f"{base}/git/trees", json=tree_payload)
        if tree_res.status_code not in (200, 201):
            raise GitHubPushError(f"github tree {tree_res.status_code}: {tree_res.text[:400]}")
        tree_sha = (tree_res.json() or {}).get("sha")
        if not tree_sha:
            raise GitHubPushError("github tree response missing sha")

        commit_body: dict[str, Any] = {
            "message": message,
            "tree": tree_sha,
        }
        if parent_sha:
            commit_body["parents"] = [parent_sha]
        commit_res = await client.post(f"{base}/git/commits", json=commit_body)
        if commit_res.status_code not in (200, 201):
            raise GitHubPushError(f"github commit-create {commit_res.status_code}: {commit_res.text[:400]}")
        new_sha = (commit_res.json() or {}).get("sha")
        if not new_sha:
            raise GitHubPushError("github commit response missing sha")

        if parent_sha and ref_res.status_code == 200:
            patch = await client.patch(
                f"{base}/git/refs/heads/{branch}",
                json={"sha": new_sha, "force": False},
            )
            if patch.status_code >= 400:
                raise GitHubPushError(f"github update-ref {patch.status_code}: {patch.text[:300]}")
        else:
            create = await client.post(
                f"{base}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": new_sha},
            )
            if create.status_code not in (200, 201):
                raise GitHubPushError(f"github create-ref {create.status_code}: {create.text[:300]}")

    html = f"https://github.com/{repo}/commit/{new_sha}"
    logger.info(f"✅ workspace pushed {len(files)} files → {html}")
    return {
        "ok": True,
        "repo": repo,
        "branch": branch,
        "sha": new_sha,
        "url": html,
        "files": [p for p, _ in files],
        "file_count": len(files),
    }


async def push_workspace_dir(root: Path, *, message: str = "Kairi workspace snapshot") -> dict[str, Any]:
    from app.routers.workspace import IGNORE_DIRS, IGNORE_EXTS

    token, repo, branch = _token_and_repo()
    files = collect_text_files(root, ignore_dirs=IGNORE_DIRS, ignore_exts=IGNORE_EXTS)
    return await push_files(files, token=token, repo=repo, branch=branch, message=message)
