# Security Policy

## Supported versions

Security fixes land on the default branch of this repository. There are no long-term support branches yet.

## What this project assumes

Kairi is a **local BYOK** app. Conversation text and API keys leave your machine only toward the LLM/search providers **you** configure. There is no Kairi-operated cloud backend for chat content.

Threat model (high level):

- Secrets live in `backend/storage/settings.json` or environment variables on your machine
- Optional `KAIRI_API_TOKEN` protects the HTTP API when bound beyond localhost
- Workspace / MCP tools can touch the filesystem — treat them as privileged
- Search and news ingest call third-party endpoints you enable

## Reporting a vulnerability

Please **do not** open a public GitHub issue for sensitive reports.

1. Email or DM the maintainer privately (see the GitHub profile linked on this repository)
2. Include: affected version/commit, reproduction steps, impact, and any suggested fix
3. Allow a reasonable window before public disclosure

## Secrets hygiene

- Never commit `backend/storage/settings.json`, `.env`, or real API keys
- If a key may have been exposed, revoke it at the provider and mint a new one (see [docs/ROTATE_SECRETS.md](docs/ROTATE_SECRETS.md))
- Public releases of this tree are intended to ship as a **fresh squash commit** without private git history

## What we will not claim

This document is not a “production ready / all passed” audit certificate. Independent review is welcome; please share findings privately first.
