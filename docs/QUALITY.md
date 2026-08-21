# Quality measurement

Kairi does not claim to beat ChatGPT or Perplexity. This tree now **measures** the same axes those products are judged on, on *this install*.

## What is recorded

Each `/api/chat` turn writes a sample into `backend/storage/latency_metrics.json`:

| Field | Meaning |
|-------|---------|
| `first_chunk_ms` | Time to first SSE `chunk` (TTFT analogue) |
| `first_sse_ms` | Time to first any SSE event |
| `search_ms` | Web search wall time |
| `supervisor_ms` | Supervisor LLM wall time (0 when skipped/cached) |
| `supervisor_skipped` | Easy-chat heuristic skipped Supervisor |
| `supervisor_loops` | Escalation loops this turn |

Integrity badge → **Speed** panel reads p50/p95 TTFT and skip rate from `/api/integrity/stats` → `latency`.

Easy turns skip Supervisor when there is no search, no tools, and the utterance is short and non-hard (`KAIRI_SUPERVISOR_SKIP=0` disables). `usage.db` uses WAL like the other SQLite files. Independent search providers (weather / Wikipedia / news / general) run concurrently.

## Blind A/B protocol (human)

`evals/quality_ab.json` is a **30-task seed**, not an LLM judge. Protocol:

1. Freeze model + settings.
2. For each task, answer in Kairi and in the comparison product with the same prompt.
3. Shuffle labels; a third person picks win / lose / tie on: groundedness, latency feel, usefulness.
4. Target to discuss publicly: **≥50% win-or-tie on groundedness** for the search/citation slice. Do not advertise “beats ChatGPT.”

Hallucination stays on the existing evals (`python evals/run_evals.py`) plus violation logs.

## Related

- [GROUNDING.md](GROUNDING.md) — filter stack
- [PROMO.md](PROMO.md) — own-channel drafts from this telemetry
