# Workspace → GitHub (Render-safe)

Kairi’s chat history lives in SQLite. **Generated files do not.** On Render the disk is wiped on every deploy, which is why Workspace looked empty after a restart while the chat still had code tabs.

## What this does

Workspace → **Save all** writes editor tabs onto the server. **Push to GitHub** snapshots that tree to **your** GitHub account via the Git Data API (no `git` binary, no Docker).

If the snapshot repo does not exist, Kairi **creates it** (`POST /user/repos` or `/orgs/{owner}/repos`) and then commits. Empty repo field → `{your-github-login}/kairi-workspace`. It will not push into the product repo `owner/kairi`.

This is the Kairi app acting as you (your token). It is not a Cursor Cloud Agent and cannot run `gh repo create` on Cursor’s side.

Cloudflare Pages can then build `npm install && npm run build` from that repo. **Connecting a Pages project is still manual** in the Cloudflare dashboard — Kairi does not create Pages projects.

## Setup

1. A GitHub token with permission to **create repos and write contents**:
   - classic: `repo`
   - fine-grained: **Administration** + **Contents** (on the user or org that will own the snapshot)
2. Paste it in Settings → Promo → GitHub token, or set `KAIRI_WORKSPACE_GITHUB_TOKEN`.
3. Optional: **Workspace snapshot repo** = `owner/name` or just a name. Leave blank to create `{you}/kairi-workspace`.
4. Leave **Create the GitHub repo if it is missing** on (default).
5. In Workspace: **Save all**, then **Push to GitHub**. After the first successful push, the resolved `owner/name` is saved in settings.

Empty workspace → error (nothing to push). Token missing `repo` create → 401/403 with a hint.

Env overrides: `KAIRI_WORKSPACE_GITHUB_REPO`, `KAIRI_WORKSPACE_GITHUB_BRANCH`, `KAIRI_WORKSPACE_GITHUB_CREATE`, `KAIRI_WORKSPACE_GITHUB_PRIVATE`.

## Continue a project after Render wiped `output/`

1. Point Cloudflare Pages (or this Cloud Agent) at the snapshot repo — connect Pages yourself.
2. Or clone it locally and `npm install && npm run build`.

The three.js Kairi site that was interrupted on Render is rebuilt in-tree at [`sites/kairi-portfolio/`](../sites/kairi-portfolio/) so it cannot vanish with a dyno.
