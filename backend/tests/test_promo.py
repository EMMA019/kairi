import asyncio
import json
from pathlib import Path

from app.core.promo.collector import fingerprint_for
from app.core.promo.writer import DISCLOSURE, draft_from_metrics


def test_writer_omits_missing_and_does_not_invent_users(monkeypatch):
    copy = draft_from_metrics(
        {
            "app_version": "2.2.0",
            "filter_total_changes": 12,
            "ttft_p50_ms": 1800,
            "eval_case_count": 24,
        },
        disclose_bot=True,
        locale="en",
    )
    body = copy["body"]
    assert "2.2.0" in copy["title"]
    assert "12" in body
    assert "1800" in body
    assert "users" not in body.lower() or "invented" in DISCLOSURE.lower()
    assert "Posted by the Kairi promo scheduler" in body
    assert "million" not in body.lower()
    assert "stars" not in body.lower()


def test_fingerprint_stable_for_same_day_bucket():
    a = fingerprint_for({"app_version": "2.2.0", "filter_total_changes": 10, "ttft_p50_ms": 51})
    b = fingerprint_for({"app_version": "2.2.0", "filter_total_changes": 10, "ttft_p50_ms": 90})
    assert a == b


def test_promo_queue_duplicate(tmp_path, monkeypatch):
    import app.core.promo.store as store
    from app.core.promo.queue import enqueue_from_telemetry

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "promo.db")
    monkeypatch.setattr(
        "app.core.promo.queue.collect_telemetry",
        lambda: {"app_version": "2.2.0", "filter_total_changes": 3},
    )
    monkeypatch.setattr(
        "app.core.promo.config.promo_config",
        lambda: {
            "enabled": True,
            "auto_post": False,
            "discord": True,
            "github": False,
            "disclose_bot": True,
            "daily_cap": 1,
            "github_repo": "",
            "github_token_set": False,
            "discord_webhook_set": False,
        },
    )
    first = enqueue_from_telemetry(locale="en")
    assert first["duplicate"] is False
    assert len(first["drafts"]) == 1
    second = enqueue_from_telemetry(locale="en")
    assert second["duplicate"] is True


def test_publish_requires_webhook(tmp_path, monkeypatch):
    import app.core.promo.store as store
    from app.core.promo.publisher import PublishError, publish_draft
    from app.core.promo.store import insert_draft

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "promo.db")
    monkeypatch.setattr(
        "app.core.promo.publisher.promo_config",
        lambda: {
            "daily_cap": 1,
            "discord_webhook_set": False,
            "github_repo": "",
            "_github_token": "",
        },
    )
    row = insert_draft(
        channel="discord",
        title="t",
        body="b",
        fingerprint="abc",
        metrics_json="{}",
    )

    async def _run():
        try:
            await publish_draft(row["id"])
            return None
        except PublishError as e:
            return str(e)

    err = asyncio.run(_run())
    assert err and "DISCORD_WEBHOOK_URL" in err


def test_quality_ab_seed_has_thirty_tasks():
    path = Path(__file__).resolve().parents[1] / "evals" / "quality_ab.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["tasks"]) == 30
    assert data["scoring"]["public_claim_rule"]
