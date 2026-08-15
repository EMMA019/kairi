# Defensive patterns vs Kairi (short audit)

Mapped from `deepseek-harness/docs/defensive-patterns.md` (2026-08).

| Pattern | Kairi status |
|---|---|
| Scrub spawned env (KEY/SECRET/TOKEN/PASSWORD) | Done — `app.core.process_env.scrubbed_environ` used by sandbox host/docker CLI, jobs fallback, build_gate, codebase_search. MCP server processes intentionally keep ambient env (they often need credentials). |
| Report orthogonal outcomes (timedOut vs exitCode) | Done for `sandbox.run_command` / jobs via `format_command_result` + structured `TOOL_TIMEOUT`. |
| Contain callback exceptions in dispatcher | Already OK — `tools/hooks.py` wraps pre/post hooks. |
| Unlink link-shaped paths | Open — apply around workspace file writes (`file` / Fast Apply) before recursive deletes. |
| Dispose reaches quiescence | Partial — MCP stop uses taskkill; background jobs are daemon threads (no await on shutdown). |
| Compaction as work-continuation checkpoint | Done (prompt) — `context_compressor` asks for Primary Request / Files / Errors / Pending Jobs / Current Work / Next Step / Critical Context. Pressure threshold + shrink-verify still open. |

Priority leftovers: symlink-safe file removal; job registry cleanup on app shutdown; tool-schema-declared per-tool `timeoutMs` beyond command heuristics.
