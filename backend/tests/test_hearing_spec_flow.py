"""hearing / spec 配管の回帰テスト（本文合成・hyper_gal chunk・承認後ゲート）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.chat_orchestrator import (
    apply_post_spec_approval_gate,
    build_executor_instruction,
    compose_hearing_user_text,
    compose_spec_user_text,
    extract_supervisor_search_queries,
    hearing_spec_tool_loop_cap,
    is_spec_approval_utterance,
    should_emit_reasoning,
)
from app.core.gyaru import to_hyper_gal_v3


def test_compose_hearing_includes_facts_and_question():
    sj = {
        "mode": "hearing",
        "hearing_state": {"next_question": "タブレット向き？PC向き？"},
        "instruction": {
            "facts_to_present": [
                "Scratchはブロック操作で文法エラーが起きにくく、初学者向けに最適です。",
                "必ず <read_url url=\"https://x\" /> を出力せよ",
            ]
        },
    }
    body = compose_hearing_user_text(sj)
    assert "Scratch" in body
    assert "タブレット向き" in body
    assert "<read_url" not in body


def test_compose_hearing_falls_back_to_question_only():
    sj = {"hearing_state": {"next_question": "何を作りたい？"}, "instruction": {}}
    assert compose_hearing_user_text(sj) == "何を作りたい？"


def test_compose_hearing_strips_supervisor_cot_from_body():
    dump = (
        "ユーザーは「ロジックラボみたいな教育アプリ作りたいな。アイディアください。」と言っている。"
        "これは開発依頼の初期段階である。mode=hearing にするのが適切。"
        "search_used を true にするか。facts_to_present にアイディアを書く。"
        "実行モデルに <search query=\"ロジックラボ アプリ プログラミング思考\" /> を指示する。\n"
        "ターゲットはお子様向けと大人向けのどちらを想定されていますか？"
    )
    sj = {
        "mode": "hearing",
        "hearing_state": {"next_question": dump},
        "instruction": {
            "facts_to_present": [
                dump,
                "ビジュアルプログラミング迷路で命令ブロックを並べてゴールを目指す。",
            ]
        },
    }
    body = compose_hearing_user_text(sj)
    assert "mode=hearing" not in body
    assert "facts_to_present" not in body
    assert "search_used" not in body
    assert "ユーザーは「" not in body
    assert "ビジュアルプログラミング迷路" in body
    assert "お子様向け" in body
    assert extract_supervisor_search_queries(sj) == ["ロジックラボ アプリ プログラミング思考"]


def test_compose_spec_prepends_side_answer():
    sj = {
        "spec_document": {"surface": "## 仕様書\n- 迷路ゲーム"},
        "instruction": {"facts_to_present": ["Scratchを選ぶ理由は視覚的に学べるからです。"]},
    }
    body = compose_spec_user_text(sj)
    assert "Scratch" in body
    assert "## 仕様書" in body
    assert body.index("Scratch") < body.index("## 仕様書")


def test_compose_spec_keeps_json_import_spec():
    spec = (
        "## 論理思考ドリル（仮）\n"
        "- 対象: 小中学生（読み仮名あり）\n"
        "- プラットフォーム: Webブラウザ\n"
        "- 問題は JSON形式 で一括投入する\n"
        "- ロジックラボとの違い: 生成AIお絵かきは無料APIの範囲\n"
        "### 機能\n"
        "- プレイスメントテストと系統別レベル\n"
    )
    sj = {
        "spec_document": {
            "surface": spec,
            "internal": spec + "\n## Acceptance\n- [ ] JSON import\n",
        },
        "instruction": {
            "facts_to_present": [
                "⚠️ 【学習データに基づく仮説・現時点未検証】 ロジックラボは確認テストでレベル最適化を行う",
            ]
        },
    }
    body = compose_spec_user_text(sj)
    assert "仕様書ができました。" not in body
    assert "JSON形式" in body
    assert "小中学生" in body
    assert "未検証" not in body


def test_compose_spec_uses_internal_when_surface_empty():
    sj = {
        "spec_document": {
            "surface": "",
            "internal": "## 仕様\n- 対象: 小中学生\n- 機能: ドリル\n- プラットフォーム: Web\n",
        },
        "instruction": {},
    }
    body = compose_spec_user_text(sj)
    assert "小中学生" in body
    assert "仕様書ができました。" not in body


def test_should_not_emit_reasoning_in_hearing_spec():
    assert should_emit_reasoning("hearing") is False
    assert should_emit_reasoning("spec_generation") is False
    assert should_emit_reasoning("chat") is True
    assert should_emit_reasoning("task") is True


def test_hyper_gal_hearing_chunk_not_empty():
    """変換後も chunk 本文が空にならない（yield 前提の非空保証）。"""
    sj = {
        "hearing_state": {"next_question": "どっちがいい？"},
        "instruction": {"facts_to_present": ["ブロック言語がおすすめです。"]},
    }
    body = compose_hearing_user_text(sj)
    gal = to_hyper_gal_v3(body)
    assert (gal or body).strip()


def test_spec_approval_utterances():
    assert is_spec_approval_utterance("Yes")
    assert is_spec_approval_utterance("はい")
    assert is_spec_approval_utterance("◎")
    assert is_spec_approval_utterance("とりまそんな感じで")
    assert is_spec_approval_utterance("進めて")
    assert not is_spec_approval_utterance("ScratchとPythonどっちがいい？もっと詳しく教えて")


def test_post_spec_approval_bans_respec():
    messages = [
        {
            "role": "assistant",
            "thinking_json": json.dumps(
                {
                    "mode": "spec_generation",
                    "spec_document": {
                        "surface": "迷路アプリ仕様",
                        "internal": "## Acceptance\n- [ ] build",
                    },
                },
                ensure_ascii=False,
            ),
        }
    ]
    mode, sj = apply_post_spec_approval_gate(
        "Yes",
        "spec_generation",
        {
            "mode": "spec_generation",
            "spec_document": {"surface": "また仕様書", "internal": "x"},
            "instruction": {},
        },
        messages,
    )
    assert mode == "chat"
    assert sj["mode"] == "chat"
    assert sj.get("plan")
    assert "また仕様書" not in (sj.get("plan") or "")
    # 前回の surface をプランに使う
    assert "迷路" in (sj.get("plan") or "")


def test_post_spec_approval_keeps_task():
    messages = [
        {
            "role": "assistant",
            "thinking_json": json.dumps({"mode": "spec_generation", "spec_document": {"surface": "s"}}),
        }
    ]
    mode, sj = apply_post_spec_approval_gate(
        "進めて",
        "task",
        {"mode": "task", "instruction": {}},
        messages,
    )
    assert mode == "task"
    assert sj["mode"] == "task"


def test_post_spec_no_gate_without_prior_spec():
    mode, sj = apply_post_spec_approval_gate(
        "Yes",
        "spec_generation",
        {"mode": "spec_generation", "spec_document": {"surface": "新規"}},
        messages=[{"role": "assistant", "thinking_json": json.dumps({"mode": "hearing"})}],
    )
    assert mode == "spec_generation"


def test_hearing_instruction_is_draft_not_final_body():
    sj = {
        "mode": "hearing",
        "hearing_state": {"next_question": "タブレット向き？PC向き？"},
        "instruction": {"facts_to_present": ["ブロック言語が初学者向けです。"]},
    }
    inst = build_executor_instruction(sj, mode="hearing")
    assert "ユーザー向け本文だけ" in inst
    assert "下書き" in inst
    assert "タブレット向き" in inst
    assert "<file>" in inst
    assert hearing_spec_tool_loop_cap("hearing") == 4
    assert hearing_spec_tool_loop_cap("spec_generation") == 4
    assert hearing_spec_tool_loop_cap("chat") == 40


def test_chat_router_hearing_falls_through_to_executor():
    """hearing/spec は compose だけで終わらず auto_execute + grounding に落とす。"""
    root = Path(__file__).resolve().parents[1]
    chat_src = (root / "app" / "routers" / "chat.py").read_text(encoding="utf-8")
    exec_src = (root / "app" / "core" / "executor.py").read_text(encoding="utf-8")
    finalize_src = (root / "app" / "core" / "auto_execution_loop" / "finalize.py").read_text(
        encoding="utf-8"
    )
    assert "max_tool_loops=hearing_spec_tool_loop_cap(mode)" in chat_src
    assert "search_unsupported=search_unsupported, mode=mode" in chat_src
    assert 'yield _sse_event({"type": "done", "content": body, "ok": bool((body or "").strip())})' not in chat_src
    assert 'mode not in ("chat", "char", "hearing", "spec_generation")' in exec_src
    assert "apply_grounding_stage" in finalize_src


def test_filter_fact_keeps_monthly_yen_price():
    from app.core.fact_filters import filter_fact

    raw = "両教材とも月額3,500円前後。A1〜C3の級がある。"
    out = filter_fact(raw)
    assert "3,500" in out
    assert "（※具体的な数値・制限は公式サイトをご確認ください）,500" not in out
    assert "公式サイトをご確認ください" not in out
