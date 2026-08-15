"""Workspace build gate using process exit codes (not keyword matching)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _npm_cmd() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def run_workspace_build(
    workspace: str | Path,
    *,
    timeout_sec: int = 240,
) -> dict[str, Any]:
    """
    If package.json exists: npm run build (exit code).
    Else if Python project: skip as success with note.
    Returns {success, exit_code, output, command}.
    """
    ws = Path(workspace)
    if not ws.is_dir():
        return {
            "success": False,
            "exit_code": -1,
            "output": f"workspace missing: {ws}",
            "command": None,
        }

    pkg = ws / "package.json"
    if pkg.exists():
        npm = _npm_cmd()
        # Prefer local node binaries on PATH for scripts
        from app.core.process_env import scrubbed_environ

        env = scrubbed_environ()
        node_bin = ws / "node_modules" / ".bin"
        if node_bin.is_dir():
            env["PATH"] = str(node_bin) + os.pathsep + env.get("PATH", "")

        cmd = [npm, "run", "build"]
        logger.info(f"🏗️ Build gate: {' '.join(cmd)} (cwd={ws})")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                env=env,
                shell=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            ok = proc.returncode == 0
            if not ok:
                # fallback: tsc -b via node
                tsc = ws / "node_modules" / "typescript" / "bin" / "tsc"
                if tsc.exists():
                    logger.info("🏗️ npm run build failed — trying node tsc -b")
                    proc2 = subprocess.run(
                        ["node", str(tsc), "-b"],
                        cwd=str(ws),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout_sec,
                        env=env,
                    )
                    out2 = (proc2.stdout or "") + (proc2.stderr or "")
                    return {
                        "success": proc2.returncode == 0,
                        "exit_code": proc2.returncode,
                        "output": out[-4000:] + "\n--- tsc -b ---\n" + out2[-4000:],
                        "command": "npm run build || node tsc -b",
                    }
            return {
                "success": ok,
                "exit_code": proc.returncode,
                "output": out[-8000:],
                "command": "npm run build",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "output": f"build timed out after {timeout_sec}s",
                "command": "npm run build",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "output": str(e),
                "command": "npm run build",
            }

    # No JS project — treat as N/A success (Python-only etc.)
    return {
        "success": True,
        "exit_code": 0,
        "output": "no package.json; build gate skipped",
        "command": None,
        "skipped": True,
    }


GATE_PASS = "pass"
GATE_FAIL = "fail"
GATE_UNVERIFIED = "unverified"


def run_completion_gate(
    workspace: str | Path,
    *,
    spec_internal: Optional[str] = None,
    skip_build_if_no_package: bool = True,
) -> dict[str, Any]:
    """
    Run acceptance + build and grade the result.

    verdict is one of:
      pass       — at least one check actually ran and everything passed
      fail       — a check ran and failed
      unverified — nothing was checked (no acceptance items, build skipped)

    An empty checklist is not evidence of success, so it must not be graded
    as a pass. `ok` stays "not failing" so callers that only retry on failure
    keep their existing behaviour.
    """
    from app.core.acceptance_checker import run_acceptance_checks

    ws = Path(workspace)
    acceptance = run_acceptance_checks(ws, spec_internal=spec_internal)
    need_build = (ws / "package.json").exists()
    if need_build or not skip_build_if_no_package:
        build = run_workspace_build(ws)
    else:
        build = {
            "success": True,
            "exit_code": 0,
            "output": "build skipped",
            "skipped": True,
        }

    has_acceptance = bool(acceptance.results)
    build_ran = not build.get("skipped")
    build_ok = bool(build.get("success"))

    if not build_ok or (has_acceptance and not acceptance.passed):
        verdict = GATE_FAIL
    elif has_acceptance or build_ran:
        verdict = GATE_PASS
    else:
        verdict = GATE_UNVERIFIED

    return {
        "ok": verdict != GATE_FAIL,
        "verdict": verdict,
        "checked": has_acceptance or build_ran,
        "acceptance": acceptance.to_dict(),
        "acceptance_report": acceptance,
        "build": build,
    }
