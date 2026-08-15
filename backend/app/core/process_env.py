"""Scrub secrets from subprocess environments (dsh defensive-patterns)."""
from __future__ import annotations

import os
from typing import Mapping, Optional

# Substrings matched case-insensitively against env var *names*
_SECRET_NAME_MARKERS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE",
    "API_KEY",
    "ACCESS_KEY",
    "AUTH",
)

# Explicit allowlist: keep these even if name matches a marker (PATH etc. never match)
_KEEP_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TZ",
        "USERNAME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "OLDPWD",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "NODE_ENV",
        "npm_config_cache",
    }
)

# Prefix allow: Windows / locale plumbing
_KEEP_PREFIXES = (
    "PROCESSOR_",
    "ProgramFiles",
    "ProgramData",
    "COMMONPROGRAMFILES",
    "LOCALAPPDATA",
    "APPDATA",
    "PUBLIC",
    "ALLUSERSPROFILE",
)


def _is_secret_name(name: str) -> bool:
    upper = (name or "").upper()
    if not upper:
        return True
    if name in _KEEP_EXACT or upper in {k.upper() for k in _KEEP_EXACT}:
        return False
    for p in _KEEP_PREFIXES:
        if upper.startswith(p.upper()):
            return False
    return any(m in upper for m in _SECRET_NAME_MARKERS)


def scrubbed_environ(
    base: Optional[Mapping[str, str]] = None,
    *,
    extra: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """
    Return a copy of the environment safe to pass to model-driven subprocesses.

    Drops names containing KEY/SECRET/TOKEN/PASSWORD/etc. so API credentials
    cannot leak via `env`/`printenv` into tool results / model context.
    """
    src = dict(base if base is not None else os.environ)
    out: dict[str, str] = {}
    for k, v in src.items():
        if v is None:
            continue
        if _is_secret_name(str(k)):
            continue
        out[str(k)] = str(v)
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            # extras are intentional (e.g. PATH prepend) — still scrub secret names
            if _is_secret_name(str(k)):
                continue
            out[str(k)] = str(v)
    return out


def format_tool_timeout_result(
    *,
    timeout_sec: int,
    command: str = "",
    partial_stdout: str = "",
    partial_stderr: str = "",
    exit_code: Optional[int] = None,
) -> str:
    """Structured timeout report (orthogonal facts; dsh-inspired TOOL_TIMEOUT)."""
    cmd = (command or "").strip().replace("\n", " ")[:200]
    lines = [
        "[TOOL_TIMEOUT]",
        "isError: true",
        "code: TOOL_TIMEOUT",
        "timedOut: true",
        f"timeoutSec: {int(timeout_sec)}",
        f"exitCode: {exit_code if exit_code is not None else '(none)'}",
        f"command: {cmd or '(unknown)'}",
    ]
    if partial_stdout:
        lines.append("--- stdout (partial) ---")
        lines.append(partial_stdout[:4000])
    if partial_stderr:
        lines.append("--- stderr (partial) ---")
        lines.append(partial_stderr[:4000])
    lines.append(
        "Note: This is a timeout, not a generic execution failure. "
        "Do not retry the identical command blindly; shorten the work or raise the budget."
    )
    return "\n".join(lines)


def format_command_result(
    *,
    stdout: str,
    stderr: str,
    exit_code: int,
    timed_out: bool = False,
    timeout_sec: Optional[int] = None,
    command: str = "",
) -> str:
    """Report exitCode / timedOut independently (never nest one inside the other)."""
    if timed_out:
        return format_tool_timeout_result(
            timeout_sec=timeout_sec or 0,
            command=command,
            partial_stdout=stdout or "",
            partial_stderr=stderr or "",
            exit_code=exit_code,
        )
    output = (stdout or "") + (("\n" + stderr) if stderr else "")
    header = f"[exitCode: {exit_code}; timedOut: false]"
    if not output.strip():
        if exit_code == 0:
            return f"{header}\n[コマンドは成功しましたが、出力はありません]"
        return f"{header}\n[コマンドはエラーコード {exit_code} で失敗しました。出力はありません]"
    if len(output) > 20000:
        output = output[:10000] + "\n\n... (出力が長すぎるため省略されました) ...\n\n" + output[-10000:]
    return f"{header}\n{output}"


_BUILD_KEYWORDS = (
    "npm install",
    "npm i",
    "npm run build",
    "create-vite",
    "create-next-app",
    "npx",
    "yarn",
    "pnpm",
    "cargo",
    "pip install",
    "pytest",
    "jest",
    "tsc",
)


def resolve_command_timeout(command: str, default: int = 60) -> int:
    """Per-command budget: builds/tests get 300s, otherwise default."""
    cmd = (command or "").lower()
    if any(kw in cmd for kw in _BUILD_KEYWORDS) and default <= 60:
        return 300
    return default
