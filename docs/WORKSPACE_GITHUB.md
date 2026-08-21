# Durable Workspace + GitHub

Chat survived Render redeploys because it lives in **the same cloud DB as Turso / `conversations.db`**. Generated files did not: they were written to repo-root `output/`, which Render wipes.

That split was the bug. Workspace files now use the **same store as chat**. The local directory is only a working copy for tools and the sandbox.

## Where files live

1. **Cloud DB** (`workspace_files` in Turso if `TURSO_DATABASE_URL` is set, otherwise `backend/storage/conversations.db`) — write-through on every `<file>` / Save.
2. **Working copy** — `backend/storage/workspace/` (override with `KAIRI_WORKSPACE_ROOT`, e.g. a Render persistent disk). Not repo-root `output/`.
3. **GitHub** — if a token is set, Kairi **creates the repo if missing** and auto-pushes a couple of seconds after the last write. Empty repo field → `{your-github-login}/kairi-workspace`. Never pushes into the product repo `kairi`.

On boot: restore from the cloud DB; if the working copy is still empty, pull from GitHub.

The LLM is instructed to treat this as durable and **not** ask you to save, ZIP, or click Push.

Cloudflare Pages is still a manual connect in the Cloudflare dashboard.

## Setup (once)

1. Keep using Turso for chat if you already do — workspace files ride along.
2. GitHub token with **create + contents write**:
   - classic: `repo`
   - fine-grained: Administration + Contents
3. Paste it in Settings → Promo → GitHub token (or `KAIRI_WORKSPACE_GITHUB_TOKEN`).
4. Leave **Push to GitHub automatically** and **Create if missing** on.

Then 「よろしく」 / `<file>` is enough. No human Push click.

Env: `KAIRI_WORKSPACE_ROOT`, `KAIRI_WORKSPACE_GITHUB_REPO`, `KAIRI_WORKSPACE_GITHUB_BRANCH`, `KAIRI_WORKSPACE_GITHUB_CREATE`, `KAIRI_WORKSPACE_GITHUB_PRIVATE`, `KAIRI_WORKSPACE_GITHUB_AUTO`, `KAIRI_WORKSPACE_GITHUB_TOKEN`.

The interrupted three.js Kairi site is also in git at [`sites/kairi-portfolio/`](../sites/kairi-portfolio/).
