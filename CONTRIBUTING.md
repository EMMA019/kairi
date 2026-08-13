# Contributing to Kairi

Thanks for helping. The most valuable contributions make the grounding layer stricter without making ordinary chat worse.

## Highest-value path: hallucination → eval case

1. Reproduce a bad answer (or press the in-app violation control).
2. From `backend/`:

   ```bash
   python evals/from_violations.py --write
   ```

3. Edit the draft under `evals/drafts/`: fill `expectations` (`must_not_contain`, optional `golden_output`).
4. Move the file to `evals/cases/` (or use `--promote` carefully).
5. Run:

   ```bash
   python evals/run_evals.py
   python evals/run_golden.py --record   # only if intentionally updating snapshots
   python evals/run_golden.py --check
   ```

## Everyday development

```bash
# backend
cd backend && pip install -r requirements.txt
python -m pytest tests -q
python evals/run_evals.py

# frontend
cd frontend && npm ci && npm test && npm run typecheck
```

## Pull requests

- Prefer small PRs with a clear failure mode and a test/eval that would have caught it.
- Do not commit `backend/storage/settings.json`, `.env`, `*.db`, `storage/`, or `booth/`.
- Do not add AGPL code (e.g. vendoring worldmonitor).
- Keep user-facing default locale **English** in examples and `settings.example.json`.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
