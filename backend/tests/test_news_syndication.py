"""Syndication / content fingerprint demotion."""
from app.core.news.syndication import (
    annotate_syndication,
    content_fingerprint,
    demote_syndicated,
    normalize_headline,
)


def test_normalize_strips_source_suffix():
    a = normalize_headline("Fed holds rates - Reuters")
    b = normalize_headline("Fed holds rates | CNBC")
    assert a == b == "fed holds rates"


def test_same_story_same_fingerprint():
    fp1 = content_fingerprint(
        {"title": "NVIDIA beats estimates - Reuters", "summary": "Chip giant reported..."}
    )
    fp2 = content_fingerprint(
        {"title": "NVIDIA beats estimates | Yahoo", "summary": "Chip giant reported..."}
    )
    assert fp1 and fp1 == fp2


def test_annotate_marks_later_as_syndicated():
    items = [
        {
            "title": "Big merger announced - Reuters",
            "summary": "Two firms agree",
            "is_high_trust_source": True,
            "importance": 80,
        },
        {
            "title": "Big merger announced | MarketWatch",
            "summary": "Two firms agree",
            "is_high_trust_source": False,
            "importance": 70,
        },
        {
            "title": "Unrelated weather alert",
            "summary": "Storms expected",
            "importance": 40,
        },
    ]
    out = annotate_syndication(items)
    independents = [x for x in out if x["independence"] == "independent"]
    syndicated = [x for x in out if x["independence"] == "syndicated"]
    assert len(independents) == 2
    assert len(syndicated) == 1
    assert syndicated[0]["is_high_trust_source"] is False


def test_demote_lowers_syndicated_importance():
    items = [
        {"title": "Same headline", "summary": "body", "importance": 90, "is_high_trust_source": True},
        {"title": "Same headline", "summary": "body", "importance": 90, "is_high_trust_source": False},
    ]
    out = demote_syndicated(items)
    assert out[0]["independence"] == "independent"
    assert out[0]["importance"] == 90
    assert out[1]["independence"] == "syndicated"
    assert out[1]["importance"] < 90
