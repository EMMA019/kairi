"""Graded news feed health."""
from datetime import datetime, timedelta

from app.core.news.health_status import (
    COVERAGE_PARTIAL,
    DEGRADED,
    HEALTHY,
    OK,
    SEED_ERROR,
    STALE_SEED,
    UNHEALTHY,
    WARNING,
    grade_feed,
    grade_fleet,
)


def test_grade_feed_ok():
    now = datetime(2026, 8, 12, 12, 0, 0)
    g = grade_feed(
        {
            "feed_name": "cnbc",
            "consecutive_failures": 0,
            "last_item_count": 5,
            "last_success": "2026-08-12 10:00:00",
        },
        now=now,
    )
    assert g["status"] == OK


def test_grade_feed_stale_and_error():
    now = datetime(2026, 8, 12, 12, 0, 0)
    stale = grade_feed(
        {
            "feed_name": "old",
            "consecutive_failures": 0,
            "last_item_count": 3,
            "last_success": (now - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S"),
        },
        now=now,
    )
    assert stale["status"] == STALE_SEED

    err = grade_feed(
        {"feed_name": "dead", "consecutive_failures": 5, "last_item_count": 0},
        now=now,
    )
    assert err["status"] == SEED_ERROR

    soft = grade_feed(
        {
            "feed_name": "flaky",
            "consecutive_failures": 1,
            "last_item_count": 2,
            "last_success": "2026-08-12 11:00:00",
        },
        now=now,
    )
    assert soft["status"] == COVERAGE_PARTIAL


def test_fleet_verdicts():
    now = datetime(2026, 8, 12, 12, 0, 0)
    ok_feed = {
        "feed_name": "a",
        "consecutive_failures": 0,
        "last_item_count": 4,
        "last_success": "2026-08-12 11:00:00",
    }
    dead = {"feed_name": "b", "consecutive_failures": 4, "last_item_count": 0}

    healthy = grade_fleet([ok_feed], pool_total=10, pool_last_18h=5, now=now)
    assert healthy["verdict"] == HEALTHY
    assert healthy["ok"] is True

    warn = grade_fleet(
        [ok_feed, {**ok_feed, "feed_name": "c", "consecutive_failures": 1}],
        pool_total=10,
        pool_last_18h=5,
        now=now,
    )
    assert warn["verdict"] == WARNING
    assert warn["status_counts"][COVERAGE_PARTIAL] == 1

    unhealthy = grade_fleet(
        [dead, {**dead, "feed_name": "d"}],
        pool_total=0,
        pool_last_18h=0,
        now=now,
    )
    assert unhealthy["verdict"] == UNHEALTHY
    assert unhealthy["ok"] is False

    degraded = grade_fleet(
        [dead, ok_feed, {**dead, "feed_name": "e"}],
        pool_total=0,
        pool_last_18h=0,
        now=now,
    )
    assert degraded["verdict"] in (DEGRADED, UNHEALTHY)
