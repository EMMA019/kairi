#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for Kairi (FastAPI backend + React/Vite frontend).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The base image ships Python 3.12 but without the stdlib venv/ensurepip module.
# Install it once; skip when already available so repeated installs stay fast.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

# --- Backend: isolated virtualenv with runtime + CI test dependencies ---
cd "$REPO_ROOT/backend"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Mirror the extra packages installed by .github/workflows/ci.yml so the
# backend test suite and evals run exactly like CI.
.venv/bin/pip install pytest anyio pyyaml httpx

# --- Frontend: reproducible install from the committed lockfile ---
cd "$REPO_ROOT/frontend"
npm ci
