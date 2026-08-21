# Workspace → GitHub (Render-safe)

Kairi’s chat history lives in SQLite. **Generated files do not.** On Render the disk is wiped on every deploy, which is why Workspace looked empty after a restart while the chat still had code tabs.

## What this does

Workspace → **Save all** writes editor tabs onto the server. **Push to GitHub** snapshots that tree to **your** repo via the Git Data API (no `git` binary, no Docker).

Cloudflare Pages can then build `npm install && npm run build` from that repo — the same split this Cloud Agent uses: files persist in git, builds happen off Render.

## Setup

1. Create an **empty** GitHub repo (example: `EMMA019/kairi-portfolio`).
2. A token with `contents:write` on that repo → Settings → Promo → GitHub token, or `KAIRI_WORKSPACE_GITHUB_TOKEN`.
3. Set **Workspace snapshot repo** to `owner/name` (Settings → Promo).
4. In Workspace: **Save all**, then **Push to GitHub**.

Empty workspace → error (nothing to push). Missing repo → create it first; Kairi will not create repositories for you.

## Continue a project after Render wiped `output/`

1. Point Cloudflare Pages (or this Cloud Agent) at the snapshot repo.
2. Or clone it locally and `npm install && npm run build`.

The three.js Kairi site that was interrupted on Render is rebuilt in-tree at [`sites/kairi-portfolio/`](../sites/kairi-portfolio/) so it cannot vanish with a dyno.
