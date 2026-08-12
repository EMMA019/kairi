"""違和感ログ永続化・英語ラベル正規化のテスト。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.violation_log import (
    append_violation_log,
    list_violation_logs,
    normalize_violation_type,
)


def test_normalize_english_and_japanese_labels():
    assert normalize_violation_type("Unsolicited Proposal") == "先回り提案"
    assert normalize_violation_type("検索スキップ") == "検索スキップ"
    assert normalize_violation_type("weird") == "その他"


def test_append_and_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.core.violation_log.VIOLATION_LOG_DIR",
        tmp_path / "violation_logs",
    )
    entry = append_violation_log(
        session_id="s1",
        user_message="今日の市況は？",
        ai_response="検索せずに答えます",
        violation_type="Search Skipped",
        reason="auto",
        source="supervisor",
    )
    assert entry["violation_type"] == "検索スキップ"
    assert entry["source"] == "supervisor"

    date, logs = list_violation_logs()
    assert date
    assert len(logs) == 1
    assert logs[0]["violation_type"] == "検索スキップ"
    # ファイル実体
    files = list((tmp_path / "violation_logs").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data[0]["session_id"] == "s1"
