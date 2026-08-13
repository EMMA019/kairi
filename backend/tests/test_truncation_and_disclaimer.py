"""途切れ検知・注意喚起（本文非付与 / UI常設）の回帰テスト。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.fact_filters.filter_metrics import (
    get_filter_metrics_snapshot,
    reset_filter_metrics,
)
from app.core.fact_filters.markup import looks_incomplete_output
from app.core.fact_filters.safety import enforce_variable_numerical_claims
from app.routers.settings import app_settings


@pytest.fixture(autouse=True)
def restore_locale():
    """app_settings.update はディスクへ永続化するため、実設定を汚さないよう戻す。"""
    original = app_settings.get().get("locale", "en")
    yield
    app_settings.update({"locale": original})


def test_looks_incomplete_trailing_backtick():
    text = (
        "ツール\t用途\n"
        "<run_command>\tコマンド実行\n"
        "`\n"
    )
    assert looks_incomplete_output(text)


def test_looks_incomplete_markdown_table_mid_cell():
    text = (
        "項目\t詳細\n"
        "---|---\n"
        "| ツール実行能力 | コマンド実行（`<run_command>`）・URLスクレイピング（`\n"
    )
    # pipe table variant
    text2 = "| ツール実行能力 | URLスクレイピング（`"
    assert looks_incomplete_output(text2)


def test_looks_incomplete_japanese_no_period():
    text = "これは十分な長さのある日本語の文章ですが、途中で切れて句点や閉じ括弧なしで終わっている状態そのものです"
    assert looks_incomplete_output(text)


def test_complete_japanese_ok():
    text = "これは十分な長さのある日本語の文章で、きちんと句点で終わります。"
    assert not looks_incomplete_output(text)


def test_self_intro_no_body_disclaimer():
    text = (
        "私はWeb検索・情報収集として最新ニュースや市場データ、観光情報などの収集ができます。"
        "投資助言はしません。「70%上昇」等の確度の数値化もしません。"
    )
    out = enforce_variable_numerical_claims(text, "", user_input="あなたってどんなAI？")
    assert "AIは間違えることがあります" not in out
    assert "お出かけ前" not in out
    assert "※一部の比率" not in out


def test_ai_diff_meta_no_body_disclaimer():
    text = (
        "金融・市場分析における厳格なルールとして、投資助言や「確度70%」などの数値化は行いません。"
        "口調の100%一貫維持も徹底します。"
    )
    out = enforce_variable_numerical_claims(text, "", user_input="ほかのAIエージェントとの違いは？")
    assert "AIは間違えることがあります" not in out


def test_travel_and_market_do_not_append_body_disclaimer():
    """未検証数値があっても本文末尾に注記を付けない（UI常設へ移行）。"""
    reset_filter_metrics()
    travel = enforce_variable_numerical_claims(
        "ランチは2,500円が目安です。",
        "",
        user_input="観光スポット教えて",
    )
    market = enforce_variable_numerical_claims(
        "日経平均は一時700円超下落。半導体セクターは約4%安となりました。",
        "[1] Nikkei fell; semiconductor sector weaker.",
        user_input="今日の日本市場どうだった？",
    )
    for out in (travel, market):
        assert "AIは間違えることがあります" not in out
        assert "AI can make mistakes" not in out
        assert "お出かけ前" not in out
        assert "※一部の比率" not in out
    snap = get_filter_metrics_snapshot()
    assert snap["changed"].get("ai_caution_signal", 0) >= 1


def test_ungrounded_percent_with_source_signals_without_body_text():
    reset_filter_metrics()
    text = "NVDAは12.5%下落し、時価総額は大きく縮みました。"
    out = enforce_variable_numerical_claims(
        text,
        "[1] NVDA fell sharply on the session. Exact percentage not stated.",
        user_input="NVDAどうだった？",
    )
    assert out == text  # 本文は変えない
    assert get_filter_metrics_snapshot()["changed"].get("ai_caution_signal", 0) >= 1
