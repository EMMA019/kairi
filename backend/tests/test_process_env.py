"""process_env scrubbing + TOOL_TIMEOUT formatting."""
from __future__ import annotations

import os

from app.core.process_env import (
    scrubbed_environ,
    format_tool_timeout_result,
    format_command_result,
    resolve_command_timeout,
    _is_secret_name,
)
from app.core.auto_execution_loop.heuristics import _detect_error


def test_scrubs_api_keys_keeps_path():
    base = {
        "PATH": "/usr/bin",
        "DEEPSEEK_API_KEY": "sk-secret",
        "BRAVE_API_KEY": "brave-secret",
        "HOME": "/home/u",
        "MY_TOKEN": "tok",
        "DB_PASSWORD": "pw",
        "NORMAL_FLAG": "1",
    }
    out = scrubbed_environ(base)
    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/home/u"
    assert out["NORMAL_FLAG"] == "1"
    assert "DEEPSEEK_API_KEY" not in out
    assert "BRAVE_API_KEY" not in out
    assert "MY_TOKEN" not in out
    assert "DB_PASSWORD" not in out


def test_secret_name_markers():
    assert _is_secret_name("OPENAI_API_KEY")
    assert _is_secret_name("auth_token")
    assert not _is_secret_name("PATH")
    assert not _is_secret_name("LANG")


def test_tool_timeout_structured_and_detectable():
    text = format_tool_timeout_result(timeout_sec=60, command="sleep 999", partial_stdout="hi")
    assert "[TOOL_TIMEOUT]" in text
    assert "code: TOOL_TIMEOUT" in text
    assert "timedOut: true" in text
    assert _detect_error(text)
    assert "TOOL_TIMEOUT" in _detect_error(text)


def test_command_result_reports_exit_independently():
    text = format_command_result(stdout="ok", stderr="", exit_code=0)
    assert "exitCode: 0" in text
    assert "timedOut: false" in text
    assert "ok" in text


def test_resolve_command_timeout_build_budget():
    assert resolve_command_timeout("npm run build") == 300
    assert resolve_command_timeout("echo hi") == 60
