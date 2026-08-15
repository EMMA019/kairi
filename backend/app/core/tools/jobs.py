"""In-memory background jobs (minimal dsh-inspired job_list / job_output)."""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from typing import Any, Optional

from app.core.tools.registry import tool_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_OUTPUT_CHARS = 100_000
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _session_id(explicit: str = "") -> str:
    try:
        from app.core.tools.agent_tools import current_tool_session

        return (explicit or "").strip() or current_tool_session.get() or "latest"
    except Exception:
        return (explicit or "").strip() or "latest"


def _workspace() -> str:
    try:
        from app.routers.workspace import get_workspace_dir

        return str(get_workspace_dir())
    except Exception:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[2] / "workspace")


def _run_job(job_id: str, command: str, session_id: str, workspace: str) -> None:
    output = ""
    status = "completed"
    try:
        from app.core.session_events import append_event

        append_event(session_id, "job/start", {"job_id": job_id, "command": command[:500]})
    except Exception:
        pass

    try:
        try:
            from app.core.sandbox import get_sandbox

            sb = get_sandbox(session_id, workspace)
            output = sb.run_command(command, timeout=300) or ""
            if "[TOOL_TIMEOUT]" in output or "code: TOOL_TIMEOUT" in output:
                status = "timeout"
        except Exception as e:
            logger.info("jobs: sandbox unavailable (%s); using subprocess", e)
            from app.core.process_env import (
                scrubbed_environ,
                format_command_result,
                format_tool_timeout_result,
            )

            res = subprocess.run(
                command,
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=300,
                env=scrubbed_environ(),
            )
            output = format_command_result(
                stdout=res.stdout or "",
                stderr=res.stderr or "",
                exit_code=int(res.returncode if res.returncode is not None else 1),
                command=command,
            )
            if res.returncode not in (0, None):
                status = "failed"
    except subprocess.TimeoutExpired:
        status = "timeout"
        from app.core.process_env import format_tool_timeout_result
        output = format_tool_timeout_result(timeout_sec=300, command=command)
    except Exception as e:
        status = "failed"
        output = f"[ERROR] {e}"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[: MAX_OUTPUT_CHARS // 2] + "\n…[truncated]…\n" + output[-MAX_OUTPUT_CHARS // 2 :]

    with _lock:
        job = _jobs.get(job_id)
        if job:
            job["status"] = status
            job["output"] = output
            job["ended_at"] = time.time()

    try:
        from app.core.session_events import append_event

        append_event(
            session_id,
            "job/end",
            {"job_id": job_id, "status": status, "output_len": len(output)},
        )
    except Exception:
        pass


@tool_registry.register(
    name="run_background",
    description="コマンドをバックグラウンドで実行し job_id を返す",
)
def run_background(command: str, session_id: str = "") -> str:
    if not (command or "").strip():
        return "[ERROR] command が空です"
    sid = _session_id(session_id)
    ws = _workspace()
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "session_id": sid,
        "command": command.strip(),
        "status": "running",
        "output": "",
        "started_at": time.time(),
        "ended_at": None,
        "thread": None,
    }
    t = threading.Thread(
        target=_run_job,
        args=(job_id, command.strip(), sid, ws),
        daemon=True,
        name=f"job-{job_id}",
    )
    job["thread"] = t
    with _lock:
        _jobs[job_id] = job
    t.start()
    return f"job_id={job_id} status=running (job_output / job_list で確認)"


@tool_registry.register(name="job_list", description="バックグラウンドジョブ一覧")
def job_list(session_id: str = "") -> str:
    sid = _session_id(session_id)
    with _lock:
        if sid and sid != "latest":
            items = [j for j in _jobs.values() if j.get("session_id") == sid]
        else:
            items = list(_jobs.values())
    if not items:
        return "ジョブはありません。"
    lines = [f"Jobs ({len(items)}):"]
    for j in sorted(items, key=lambda x: x.get("started_at") or 0, reverse=True):
        lines.append(f"- {j['id']} [{j['status']}] {j['command'][:80]}")
    return "\n".join(lines)


@tool_registry.register(name="job_output", description="ジョブ出力を取得")
def job_output(job_id: str) -> str:
    with _lock:
        job = _jobs.get((job_id or "").strip())
    if not job:
        return f"[ERROR] unknown job_id: {job_id}"
    out = job.get("output") or ""
    return f"job_id={job['id']} status={job['status']}\n{out or '(no output yet)'}"


@tool_registry.register(name="job_kill", description="実行中ジョブをキャンセル扱いにする（最善努力）")
def job_kill(job_id: str) -> str:
    with _lock:
        job = _jobs.get((job_id or "").strip())
        if not job:
            return f"[ERROR] unknown job_id: {job_id}"
        if job["status"] == "running":
            job["status"] = "killed"
            job["ended_at"] = time.time()
            if not job.get("output"):
                job["output"] = "[killed]"
            return f"job_id={job_id} marked killed"
        return f"job_id={job_id} already {job['status']}"
