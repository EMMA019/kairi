# Own-channel promo

Kairi can draft posts from **local telemetry** and send them only to channels you control.

It does **not** reply, DM, like, or comment on other people’s posts.

## Flow

```
collector (filters / Integrity / latency / eval count)
    → writer (telemetry sentences only; no invented stats)
    → SQLite queue (draft)
    → human approve (Settings → Promo)
    → Discord webhook and/or GitHub issue on YOUR repo
```

Auto-post is **Discord-only**, still capped (`KAIRI_PROMO_DAILY_CAP`, default 1/day). GitHub always waits for a click.

Duplicates: same coarse fingerprint within 7 days is not re-queued.

Bot disclosure is on by default (`KAIRI_PROMO_DISCLOSE_BOT=1`).

## Enable

```bash
# .env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
KAIRI_PROMO_ENABLED=1
# optional
KAIRI_PROMO_AUTO_POST=0
KAIRI_PROMO_GITHUB=1
KAIRI_PROMO_GITHUB_REPO=you/your-fork
KAIRI_PROMO_GITHUB_TOKEN=ghp_...
```

Or toggle in Settings → Promo (save settings, then Collect draft now).

The daily scheduler fires at **21:00 JST** when enabled. Manual collect does not wait.

## Policy

- Own webhook / own GitHub repo only.
- Label on GitHub issues: `kairi-promo` (create the label once, or posting may 422).
- X / Zenn / “reply to HN” are out of scope on purpose (spam / ToS).
