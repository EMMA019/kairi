"""Push the local workspace tree to GitHub (create the repo if asked).

Render disks are ephemeral. Token needs `repo` (classic) or Contents + Administration
(fine-grained) on the user/org that will own the snapshot. Never defaults to the
product repo `kairi`.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Iterable

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_FILES = 80
MAX_FILE_BYTES = 400_000
GITHUB_API = "https://api.github.com"
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def github_target(settings: dict[str, Any] | None = None) -> dict[str, Any]:
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
    create_raw = os.environ.get("KAIRI_WORKSPACE_GITHUB_CREATE")
    if create_raw is None or not str(create_raw).strip():
        create = s.get("workspace_github_create")
        create = True if create is None else bool(create)
    else:
        create = str(create_raw).strip().lower() in ("1", "true", "yes", "on")
    private_raw = os.environ.get("KAIRI_WORKSPACE_GITHUB_PRIVATE")
    if private_raw is None or not str(private_raw).strip():
        private = bool(s.get("workspace_github_private"))
    else:
        private = str(private_raw).strip().lower() in ("1", "true", "yes", "on")
    return {
        "token": token,
        "repo": repo,
        "branch": branch,
        "create": create,
        "private": private,
    }


def _token_and_repo(settings: dict[str, Any] | None = None) -> tuple[str, str, str]:
    t = github_target(settings)
    return t["token"], t["repo"], t["branch"]


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


def suggest_repo_name(workspace_name: str | None = None) -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", (workspace_name or "").strip())
    raw = raw.strip("-._") or "kairi-workspace"
    if raw.lower() in {"kairi", "output", "workspace"}:
        raw = "kairi-workspace"
    return raw[:80]


class GitHubPushError(RuntimeError):
    pass


async def _github_login(client: httpx.AsyncClient) -> str:
    res = await client.get(f"{GITHUB_API}/user")
    if res.status_code >= 400:
        raise GitHubPushError(
            f"GitHub token rejected ({res.status_code}). "
            "Use a token for YOUR account with repo create + contents write."
        )
    login = ((res.json() or {}).get("login") or "").strip()
    if not login:
        raise GitHubPushError("GitHub /user did not return a login")
    return login


def resolve_repo_spec(repo: str, login: str, workspace_name: str | None = None) -> str:
    spec = (repo or "").strip().lstrip("/")
    if not spec:
        spec = f"{login}/{suggest_repo_name(workspace_name)}"
    elif "/" not in spec:
        spec = f"{login}/{spec}"
    owner, name = spec.split("/", 1)
    owner, name = owner.strip(), name.strip()
    if not owner or not _REPO_NAME_RE.match(name):
        raise GitHubPushError(f"invalid repo name: {spec}")
    if name.lower() == "kairi" and owner.lower() == login.lower():
        # Never snapshot into the product repo by accident.
        raise GitHubPushError(
            f"refusing to push workspace into {owner}/kairi (the product repo). "
            f"Leave the field empty to create {login}/kairi-workspace, or set a different owner/name."
        )
    return f"{owner}/{name}"


def _default_branch_of(payload: dict[str, Any] | None) -> str:
    name = ((payload or {}).get("default_branch") or "").strip()
    return name or "main"


async def ensure_repo(
    client: httpx.AsyncClient,
    *,
    repo: str,
    login: str,
    create: bool,
    private: bool,
) -> tuple[str, bool, str]:
    """Return (owner/name, created, default_branch). Creates the repo when missing and create=True."""
    owner, name = repo.split("/", 1)
    base = f"{GITHUB_API}/repos/{owner}/{name}"
    got = await client.get(base)
    if got.status_code == 200:
        return repo, False, _default_branch_of(got.json())
    if got.status_code != 404:
        raise GitHubPushError(f"github {got.status_code}: {got.text[:300]}")
    if not create:
        raise GitHubPushError(
            f"repo {repo} not found. Enable create-if-missing or make the repo yourself."
        )
    payload = {
        "name": name,
        "description": "Kairi workspace snapshot (created by the local app, not a Cursor agent).",
        "private": bool(private),
        "auto_init": True,
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False,
    }
    if owner.lower() == login.lower():
        created = await client.post(f"{GITHUB_API}/user/repos", json=payload)
    else:
        created = await client.post(f"{GITHUB_API}/orgs/{owner}/repos", json=payload)
    if created.status_code not in (200, 201):
        hint = ""
        if created.status_code in (401, 403):
            hint = (
                " Token needs permission to create repositories "
                "(classic: repo; fine-grained: Administration + Contents)."
            )
        raise GitHubPushError(
            f"github create-repo {created.status_code}: {created.text[:300]}.{hint}"
        )
    html = (created.json() or {}).get("html_url") or f"https://github.com/{repo}"
    logger.info(f"✅ created GitHub repo {html}")
    # auto_init is eventually consistent
    last_json: dict[str, Any] = created.json() or {}
    for _ in range(8):
        check = await client.get(base)
        if check.status_code == 200:
            return repo, True, _default_branch_of(check.json())
        await asyncio.sleep(0.4)
    return repo, True, _default_branch_of(last_json)


async def push_files(
    files: list[tuple[str, str]],
    *,
    token: str,
    repo: str,
    branch: str,
    message: str,
    create_if_missing: bool = True,
    private: bool = False,
    workspace_name: str | None = None,
) -> dict[str, Any]:
    if not token:
        raise GitHubPushError("github_token / KAIRI_WORKSPACE_GITHUB_TOKEN is not set")
    if not files:
        raise GitHubPushError("workspace is empty — nothing to push")
    if not (repo or "").strip() and not create_if_missing:
        raise GitHubPushError(
            "set workspace repo as owner/name, or enable create-if-missing"
        )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kairi-workspace-sync",
    }

    async with httpx.AsyncClient(timeout=40.0, headers=headers) as client:
        login = await _github_login(client)
        repo = resolve_repo_spec(repo, login, workspace_name)
        repo, created, default_branch = await ensure_repo(
            client, repo=repo, login=login, create=create_if_missing, private=private
        )
        owner, _name = repo.split("/", 1)
        base = f"{GITHUB_API}/repos/{owner}/{_name}"

        parent_sha: str | None = None
        base_tree: str | None = None
        ref_res = await client.get(f"{base}/git/ref/heads/{branch}")
        if ref_res.status_code == 200:
            parent_sha = ((ref_res.json() or {}).get("object") or {}).get("sha")
        elif ref_res.status_code == 404 and branch != default_branch:
            def_res = await client.get(f"{base}/git/ref/heads/{default_branch}")
            if def_res.status_code == 200:
                parent_sha = ((def_res.json() or {}).get("object") or {}).get("sha")
                # Keep the requested branch name; we will create it from default_branch's tip.
            elif def_res.status_code not in (200, 404):
                raise GitHubPushError(
                    f"github default-ref {def_res.status_code}: {def_res.text[:300]}"
                )
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
            ref_create = await client.post(
                f"{base}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": new_sha},
            )
            if ref_create.status_code not in (200, 201):
                raise GitHubPushError(
                    f"github create-ref {ref_create.status_code}: {ref_create.text[:300]}"
                )

    html = f"https://github.com/{repo}/commit/{new_sha}"
    logger.info(f"✅ workspace pushed {len(files)} files → {html}")
    return {
        "ok": True,
        "repo": repo,
        "branch": branch,
        "sha": new_sha,
        "url": html,
        "html_url": f"https://github.com/{repo}",
        "files": [p for p, _ in files],
        "file_count": len(files),
        "repo_created": created,
    }


async def push_workspace_dir(root: Path, *, message: str = "Kairi workspace snapshot") -> dict[str, Any]:
    from app.routers.workspace import IGNORE_DIRS, IGNORE_EXTS

    target = github_target()
    files = collect_text_files(root, ignore_dirs=IGNORE_DIRS, ignore_exts=IGNORE_EXTS)
    return await push_files(
        files,
        token=target["token"],
        repo=target["repo"],
        branch=target["branch"],
        message=message,
        create_if_missing=target["create"],
        private=target["private"],
        workspace_name=root.name,
    )
