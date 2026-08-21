from app.core.supervisor_skip import should_skip_supervisor, skipped_supervisor_json


def test_skip_short_easy_chat():
    assert should_skip_supervisor(
        "What is 2+2? answer briefly",
        search_needed=False,
        mode="chat",
    )


def test_no_skip_when_search_needed():
    assert not should_skip_supervisor(
        "hello",
        search_needed=True,
        mode="chat",
    )


def test_no_skip_market_today():
    assert not should_skip_supervisor(
        "今日の日経はどうだった？",
        search_needed=False,
        mode="chat",
    )


def test_no_skip_task_or_tools():
    assert not should_skip_supervisor(
        "implement a WAL helper",
        search_needed=False,
        mode="chat",
    )
    assert not should_skip_supervisor(
        "hello",
        search_needed=False,
        mode="task",
    )


def test_skipped_json_is_executor_compatible():
    payload = skipped_supervisor_json()
    assert payload["mode"] == "chat"
    assert payload["plan"] is None
    assert payload["kv_action"]["action"] == "none"
    assert payload["supervisor_skipped"] is True
