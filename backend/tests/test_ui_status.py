"""Localized pipeline / UI status strings."""
from app.core.ui_status import disclaimer, pipeline_detail


def test_pipeline_detail_en():
    assert "Analyzing" in pipeline_detail("intent_analysis", "en")
    assert "Gathering information: foo" == pipeline_detail("searching", "en", q="foo")


def test_pipeline_detail_ja():
    assert "分析" in pipeline_detail("intent_analysis", "ja")
    assert pipeline_detail("searching", "ja", q="日経") == "情報収集中: 日経"


def test_ai_caution_disclaimer_locale():
    en = disclaimer("ai_caution", "en")
    ja = disclaimer("ai_caution", "ja")
    assert "AI can make mistakes" in en
    assert "AIは間違えることがあります" in ja
    assert "※" not in en


def test_ai_caution_is_domain_agnostic():
    """旅行/金融のドメイン語を含まない一般的な文言であること。"""
    for loc in ("ja", "en"):
        text = disclaimer("ai_caution", loc)
        for word in ("お出かけ", "店舗", "比率", "開示", "before you go", "disclosures"):
            assert word not in text


def test_has_ai_caution_detects_new_and_legacy():
    from app.core.ui_status import has_ai_caution

    assert has_ai_caution(disclaimer("ai_caution", "ja"))
    assert has_ai_caution(disclaimer("ai_caution", "en"))
    # レガシー文言も二重付与を防ぐため検出する
    assert has_ai_caution("※一部の比率はソース記事に明記されていません。")
    assert not has_ai_caution("普通の回答です。")
