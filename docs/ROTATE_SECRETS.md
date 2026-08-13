# Secret rotation

If an API key may have been exposed (local leak, shared zip, or old private history), revoke it at the provider and issue a new one.

## Typical targets

- DeepSeek / OpenAI / Anthropic / Gemini keys
- Brave (or other search) keys
- Optional `KAIRI_API_TOKEN`

## Steps

1. Revoke the old key in the provider dashboard
2. Put the new key in `backend/.env` (for example `DEEPSEEK_API_KEY=...`) or paste it in Settings → API Keys
3. Confirm `backend/storage/settings.json` is gitignored and never committed

## Local files

| Path | Role |
|------|------|
| `backend/storage/settings.json` | Runtime settings (gitignored) |
| `backend/storage/settings.example.json` | Safe template for new installs |
| `.env` / `backend/.env` | Optional env overrides (gitignored) |

IBKR (read-only): host/port/client id only in `.env`. Gateway password stays in TWS/Gateway. See [IBKR_GATEWAY.md](IBKR_GATEWAY.md).

## Public repository policy

The public GitHub tree is published from a **squash export** that does not carry private working history. Do not rely on history rewriting of the private clone as your only defense — always rotate keys if exposure is possible.
