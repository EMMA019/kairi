# -*- coding: utf-8 -*-
import pytest
from app.core.source_evaluator import (
    evaluate_source_authority,
    annotate_and_sort_search_results,
    verify_entity_claim_attribution,
)

def test_spoofed_edu_domain():
    # .edu.pl のような偽装ドメインをTier 3 & 偽装検知できるか
    res = evaluate_source_authority("https://harvard.edu.pl/trends-2026", "Lifestyle & Culture Trends - Harvard")
    assert res["is_spoofed"] is True
    assert res["tier"] == 3
    assert "偽装疑い" in res["label"]

def test_genuine_tier1_domain():
    # 本物の公的・学術機関がTier 1になるか
    res1 = evaluate_source_authority("https://www.harvard.edu/research", "Official Research")
    res2 = evaluate_source_authority("https://www.nature.com/articles/123", "Nature Paper")
    assert res1["tier"] == 1
    assert res1["is_spoofed"] is False
    assert res2["tier"] == 1

def test_tier2_media_domain():
    # 主要メディアや信頼できる調査機関がTier 2になるか
    res = evaluate_source_authority("https://www.reuters.com/markets/europe", "Reuters News")
    assert res["tier"] == 2
    assert res["is_spoofed"] is False

def test_tier3_seo_or_blog():
    # 一般ブログやSEOまとめ記事がTier 3になるか
    res = evaluate_source_authority("https://anarchydaily.com/trends-2026", "Cultural Trends 2026")
    assert res["tier"] == 3

def test_annotate_and_sort():
    # 偽装ドメインやTier3が下にソートされ、Tier1/2が上にソートされるか
    results = [
        {"url": "https://harvard.edu.pl/fake", "title": "Spoofed Harvard", "source": "Harvard.edu.pl"},
        {"url": "https://anarchydaily.com/blog", "title": "Blog", "source": "Anarchy Daily"},
        {"url": "https://www.reuters.com/news", "title": "Reuters", "source": "Reuters"},
        {"url": "https://www.nature.com/science", "title": "Nature", "source": "Nature"},
    ]
    sorted_res = annotate_and_sort_search_results(results)
    assert sorted_res[0]["tier"] == 1
    assert sorted_res[0]["domain"] == "www.nature.com"
    assert sorted_res[1]["tier"] == 2
    assert sorted_res[-1]["is_spoofed"] is True

def test_entity_claim_attribution():
    # 複数モデルが共起し、主語が曖昧な場合に警告が付与されるか
    text = "Gemma 4 E2BとKimi K2.5を比較した。同モデルはベンチマークで最高スコアを記録した。"
    is_valid, processed = verify_entity_claim_attribution(text)
    assert is_valid is False
    assert "主語要確認" in processed
