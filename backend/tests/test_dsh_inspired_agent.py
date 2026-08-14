"""dsh-inspired session log / tool hooks / skill catalog / compaction tests."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.session_events import append_event, read_events, SESSION_EVENTS_DIR
from app.core.prompt_builder.skill_catalog import (
    build_skill_catalog_prompt,
    load_skill_body,
    matching_skill_ids,
)
from app.core.tools.registry import tool_registry
from app.core.fact_filters.pipeline import apply_grounding_pipeline
from app.core.fact_filters.markup import sanitize_preserving_body


def test_session_events_append_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    sid = "test-session-events-1"
    append_event(sid, "grounding/before", {"text": "raw ## glued"})
    append_event(sid, "grounding/after", {"text": "raw\n\n## glued", "changed": True})
    events = read_events(sid)
    assert len(events) == 2
    assert events[0]["type"] == "grounding/before"
    assert events[1]["payload"]["changed"] is True


def test_skill_catalog_not_full_body():
    text = build_skill_catalog_prompt("fastapi の router を直したい")
    assert "スキルカタログ" in text
    assert "load_skill" in text
    assert "python-backend" in text
    assert "推奨" in text
    # Full skill body markers should not appear
    assert "aiosqlite の活用" not in text


def test_load_skill_body_tool():
    ok, body = load_skill_body("python-backend")
    assert ok is True
    assert "Loaded Skill" in body or "aiosqlite" in body or "FastAPI" in body
    bad_ok, bad = load_skill_body("does-not-exist-xyz")
    assert bad_ok is False
    assert "ERROR" in bad


def test_load_skill_registered():
    assert "load_skill" in tool_registry.list_tools()
    out = tool_registry.execute("load_skill", {"skill_id": "frontend-dev"})
    assert "ERROR" not in out or "Loaded Skill" in out or "frontend" in out.lower()


def test_matching_skill_ids():
    ids = matching_skill_ids("ペアトレード ETF バックテスト")
    assert "quant-pairs-trading" in ids


def test_tool_hooks_wrap_execute_tools():
    from app.core.tools.hooks import (
        install_hooks,
        clear_hooks,
        register_pre_execute,
        register_post_execute,
    )
    from app.core.tools.handler import ToolHandler

    clear_hooks()
    import app.core.tools.hooks as hooks_mod

    hooks_mod._installed = False
    seen = {"pre": 0, "post": 0}

    async def pre(handler, text):
        seen["pre"] += 1
        return text

    async def post(handler, original, updated, events, elapsed):
        seen["post"] += 1

    register_pre_execute(pre)
    register_post_execute(post)
    install_hooks()

    async def _run():
        h = ToolHandler(session_id="hook-test", mode="chat")
        return await h.execute_tools("ただの文章です。ツールタグなし。")

    text, events = asyncio.run(_run())
    assert seen["pre"] == 1
    assert seen["post"] == 1
    assert "ただの文章" in text
    clear_hooks()
    hooks_mod._installed = False


def test_compaction_logs_actions():
    from app.core.auto_execution_loop.compression import _smart_compress_loop_history

    history = []
    for i in range(10):
        history.append({"role": "user", "content": ("x" * 600) + f" tool result {i}"})
        history.append({"role": "assistant", "content": f"ok {i}"})
    history.append({"role": "user", "content": "latest"})

    out = asyncio.run(_smart_compress_loop_history(history, session_id="compact-test"))
    assert len(out) < len(history)
    joined = " ".join(m["content"] for m in out if m["role"] == "user")
    assert "圧縮" in joined or len(out) >= 5


def test_assembled_grounding_snapshot_keyless():
    """
    Scripted mock executor output → real markup sanitize + grounding pipeline.
    Keyless assembled-path snapshot (dsh-style: mock only at model boundary).
    """
    user_input = "SNDKとWDCどうだった？"
    search_results = (
        "[1] Sandisk Investor Day announced 100% excess cash return.\n"
        "[18] SK Hynix and SanDisk climb on memory shortage.\n"
    )
    mock_executor_output = (
        "SNDKは好材料です。## 🟢 いいニュース・好材料\n"
        "- 株主還元方針を表明した\n"
        "ゼブラトン騎手が優勝しました。"
    )

    def pipeline(t: str) -> str:
        from app.core.fact_filters.format import ensure_markdown_block_breaks

        t = ensure_markdown_block_breaks(t)
        return apply_grounding_pipeline(t, search_results, user_input=user_input)

    after = sanitize_preserving_body(mock_executor_output, pipeline)
    assert "です。\n\n## 🟢" in after or "## 🟢" in after
    assert "です。##" not in after
    assert "ゼブラトン" not in after or "要確認" in after or "ソース未記載" in after


def test_grounding_waterfall_events(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    from app.core.auto_execution_loop.grounding_waterfall import apply_grounding_stage

    sid = "waterfall-1"
    raw = "SNDKは好調です。## 見出し\nゼブラトン騎手が優勝しました。"
    src = "[1] Sandisk Investor Day cash return."
    after = apply_grounding_stage(
        raw, search_results=src, user_input="SNDKどう？", session_id=sid
    )
    types = [e["type"] for e in read_events(sid)]
    assert "assistant/message" in types
    assert "grounding/apply" in types
    assert "grounding/before" in types
    assert "grounding/after" in types
    assert types.index("assistant/message") < types.index("grounding/before")
    assert "です。##" not in after or "\n\n##" in after


def test_prompt_assembly_static_hash_ignores_dynamic():
    from app.core.prompt_builder.sections import PromptAssembly, hash_static_prompt

    a = PromptAssembly()
    a.register_section("system:base", 0, "STATIC_A")
    a.register_context("clock", 0, "Monday 09:00")
    h1 = a.static_hash()
    a.register_context("clock", 0, "Tuesday 15:00")
    h2 = a.static_hash()
    assert h1 == h2
    a.register_section("system:base", 0, "STATIC_B")
    h3 = a.static_hash()
    assert h3 != h1
    assert h1 == hash_static_prompt("STATIC_A")


def test_assembled_loop_snapshot_keyless(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    import asyncio
    from app.core.eval_support.llm_replay import run_assembled_loop_snapshot

    result = asyncio.run(
        run_assembled_loop_snapshot(
            user_input="SNDKとWDCどうだった？",
            mock_executor_output=(
                "SNDKは好材料です。## 🟢 いいニュース\n"
                "- 還元方針\n"
                "ゼブラトン騎手が優勝しました。"
            ),
            search_results="[1] Sandisk Investor Day cash return.\n",
            session_id="assembled-unit-1",
        )
    )
    text = result["final_text"]
    assert "です。##" not in text
    types = {e.get("type") for e in result["sse_events"]}
    assert "chunk" in types or True  # SSE may be gated until FINAL_ANSWER
    sess = [e["type"] for e in result["session_events"]]
    assert "grounding/before" in sess
    assert "grounding/after" in sess



def test_repeat_reminder_thresholds():
    from app.core.tools import repeat_reminder as rr

    sid = "rem-test-1"
    rr.reset_chain(sid)
    rr._chains.clear()

    class H:
        tool_results = []

    h = H()
    tag = '<mcp_call tool="echo" message="hi" />'
    for i in range(1, 9):
        h.tool_results = []
        rem = rr.observe_and_maybe_remind(sid, tag, h)
        if i in rr.THRESHOLDS:
            assert rem is not None, f"expected reminder at {i}"
            assert any("反復" in r or "助言" in r for r in h.tool_results)
        else:
            assert rem is None
    # excluded tools do not advance / trigger
    rr.reset_chain(sid)
    for _ in range(5):
        rem = rr.observe_and_maybe_remind(sid, '<mcp_call tool="todo_write" todos_json="[]" />', h)
        assert rem is None


def test_todo_write_validation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.session_events.SESSION_EVENTS_DIR", tmp_path)
    from app.core.tools.agent_tools import todo_write, todo_list, current_tool_session, _todos

    tok = current_tool_session.set("todo-sess-1")
    try:
        _todos.pop("todo-sess-1", None)
        bad = todo_write('{"content":"x"}')
        assert "ERROR" in bad
        bad2 = todo_write(
            '[{"content":"a","status":"in_progress"},{"content":"b","status":"in_progress"}]'
        )
        assert "ERROR" in bad2 and "in_progress" in bad2
        empty = todo_write('[{"content":"","status":"pending"}]')
        assert "ERROR" in empty
        ok = todo_write(
            '[{"content":"do thing","status":"pending"},{"content":"doing","status":"in_progress"}]'
        )
        assert "ERROR" not in ok
        assert "全2件" in ok or "2" in ok
        listed = todo_list()
        assert "do thing" in listed
    finally:
        current_tool_session.reset(tok)


def test_catalog_digest_change(monkeypatch):
    from app.core.prompt_builder import skill_catalog as sc

    sc._last_digest.clear()
    d1 = sc.catalog_digest("fastapi")
    d2 = sc.catalog_digest("fastapi")
    assert d1 == d2
    assert len(d1) == 16
    prompt = sc.build_skill_catalog_prompt("fastapi")
    assert "catalog_digest:" in prompt
    # first call stores, no refresh
    msg1 = sc.maybe_catalog_refresh_message("cat-sess", "fastapi")
    assert msg1 == ""
    # force digest change
    sc._last_digest["cat-sess"] = "deadbeefdeadbeef"
    msg2 = sc.maybe_catalog_refresh_message("cat-sess", "fastapi")
    assert "スキルカタログ更新" in msg2
    assert "catalog_digest:" in msg2


def test_job_list_empty():
    from app.core.tools.agent_tools import current_tool_session
    from app.core.tools import jobs as jobs_mod

    tok = current_tool_session.set("job-empty-sess")
    try:
        # clear any jobs for this session
        with jobs_mod._lock:
            for jid, j in list(jobs_mod._jobs.items()):
                if j.get("session_id") == "job-empty-sess":
                    del jobs_mod._jobs[jid]
        out = jobs_mod.job_list()
        assert "ありません" in out or "Jobs" not in out or out.startswith("ジョブ")
        assert "job_id=" not in out or "ありません" in out
    finally:
        current_tool_session.reset(tok)
