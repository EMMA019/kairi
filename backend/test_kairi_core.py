"""
Kairi 改修機能テストスイート (Phase 1 〜 Phase 4 & Claude Code機能)
"""
import pytest
import os
import sys

# パス追加
sys.path.insert(0, os.path.dirname(__file__))

from app.core.cache_manager import _normalize_query
from app.core.fact_filter import verify_numbers_exist_in_source
from app.core.auto_execution_loop import _detect_test_failure
from app.core.project_context import generate_tree, detect_project_type


def test_normalize_query_nfkc():
    """NFKC正規化と全角半角変換のテスト"""
    raw = "　ＡＩの　発展と　未来！２０２６年。　"
    norm = _normalize_query(raw)
    assert "aiの" in norm
    assert "2026年" in norm
    assert "未来" in norm


def test_smart_number_verification_approach_b():
    """アプローチB：スマート数値突合（M/B/万/億）のテスト"""
    source_text = "Tesla reported a net income of 25M euros in Q2 2026."
    
    # 2500万ユーロ（25Mと同値）が含まれる場合はエラーバッジが付与されないこと
    ok, res1 = verify_numbers_exist_in_source("テスラの純利益は2500万ユーロでした。", source_text)
    assert ok is True
    assert "ソース未確認数値" not in res1
    
    # ソースと異なる数値（5000万など）は未確認として検知されること（ただしタグ自動付加は廃止）
    ok2, res2 = verify_numbers_exist_in_source("テスラの純利益は5000万ユーロでした。", source_text)
    assert ok2 is False
    assert "ソース未確認数値" not in res2
    
    # 複合単位（億＋万）の突合テスト：1億2500万ポンドが 125M pounds と一致すること
    source_soccer = "Liverpool signed Alexander Isak for 125M pounds in summer 2025."
    ok3, res3 = verify_numbers_exist_in_source("イサク獲得（1億2500万ポンド）が最高額", source_soccer)
    assert ok3 is True
    assert "ソース未確認数値" not in res3


def test_detect_test_failure_enhancements():
    """テスト結果失敗解析の強化（0 passed バグの解消等）テスト"""
    # 1. pytest での失敗が正しく失敗と検知されること
    failure_log = "================== 1 failed, 2 passed in 0.5s =================="
    res = _detect_test_failure(failure_log)
    assert res is not None
    assert res["success"] is False
    assert res["framework"] == "pytest"
    
    # 2. 0 passed が成功と見なされないこと（以前のバグ解消）
    zero_passed_log = "================== 0 passed in 0.1s =================="
    res_zero = _detect_test_failure(zero_passed_log)
    # _detect_test_failure で None または success: False が返るかチェック
    if res_zero is not None:
        assert res_zero["success"] is False


def test_project_context():
    """プロジェクトコンテキスト自動収集のテスト"""
    ws_dir = os.path.dirname(__file__)  # backendフォルダ
    tree = generate_tree(ws_dir, max_depth=1)
    assert "app/" in tree or "📁" in tree
    
    proj_type = detect_project_type(ws_dir)
    assert "Python" in proj_type or "汎用" in proj_type


def test_prohibit_jpy_conversion_for_foreign_currency():
    """外貨金額における勝手な日本円換算（（約〇〇億円）等）の除去テスト"""
    from app.core.fact_filter import check_currency_consistency, filter_fact
    
    raw_text = "30億ポンド（約5700億円） を支出しとるねんって。イサク獲得（1億2500万ポンド＝約237億円） が最高額。"
    _, cleaned = check_currency_consistency(raw_text)
    assert "5700億円" not in cleaned
    assert "237億円" not in cleaned
    assert "30億ポンド" in cleaned
    assert "1億2500万ポンド" in cleaned
    
    fact = "プレミアリーグの市場支出は30億ポンド（日本円で約5,700億円相当）に達した"
    cleaned_fact = filter_fact(fact)
    assert "5,700億円" not in cleaned_fact
    assert "30億ポンド" in cleaned_fact


def test_user_case_285m_euros():
    """ユーザー指摘ケース：€285m（約2億8500万ユーロ！）で8500万が未確認にならないこと"""
    source_text = "Chelsea €285m 5-man shortlist after Granit Xhaka rejection"
    ok, res = verify_numbers_exist_in_source("移籍金総額なんと €285m（約2億8500万ユーロ！） 相当の5名", source_text)
    assert ok is True
    assert "ソース未確認数値" not in res


def test_prohibit_currency_conflation():
    """異なる外貨同士の混同や同一視並記（47億ドル（約47億ユーロ）等）の除去テスト"""
    from app.core.fact_filter import check_currency_consistency, filter_fact
    
    raw_text = "GoogleがEUから47億ドル（約47億ユーロ）の制裁金を科された。さらに41億ユーロ＝約47億ドルの罰金。"
    _, cleaned = check_currency_consistency(raw_text)
    assert "47億ユーロ" not in cleaned
    assert "47億ドル" in cleaned
    assert "41億ユーロ" in cleaned
    
    fact = "47億ドル（約47億ユーロ）の制裁金が確定"
    cleaned_fact = filter_fact(fact)
    assert "（約47億ユーロ）" not in cleaned_fact
    assert "47億ドル" in cleaned_fact


def test_abolish_unverified_number_badge():
    """ユーザー指示①の検証：未確認数値が検出された場合でも「ソース未確認数値」タグが付加されないこと"""
    source_text = "Micron reported Q3 capex of $7.0B."
    ok, res = verify_numbers_exist_in_source("Q3設備投資70億ドル、通期で250億ドルに引き上げ", source_text)
    assert ok is False
    assert "ソース未確認数値" not in res
    assert "⚠️" not in res


def test_typo_correction_ream_to_risk():
    """進行形タイポ対策：『未入金リーム』『連鎖倒産リーム』が『リスク』へ自動補正されること"""
    from app.core.fact_filter import correct_common_typos, filter_fact
    
    raw_text = "未入金リーム：全東信が立て替えてくれるはずやった売上代金が未払いのまま回収できへん可能性がある。"
    corrected = correct_common_typos(raw_text)
    assert "未入金リスク" in corrected
    assert "未入金リーム" not in corrected
    
    raw_text2 = "飲食店やキャバクラの連鎖倒産リームや、信用リーム、システムのシシテム障害に注意。"
    corrected2 = filter_fact(raw_text2)
    assert "連鎖倒産リスク" in corrected2
    assert "信用リスク" in corrected2
    assert "システム障害" in corrected2
    assert "リーム" not in corrected2


def test_strip_unverified_day_of_week():
    """曜日間違いハルシネーション防衛：ソースに記載がない/不一致の曜日（（火）等）表記を自動削除すること"""
    from app.core.fact_filter import strip_unverified_day_of_week, filter_fact

    # 1. 2026年7月13日は実際には月曜だがAIが（火）と書いた場合、ソースにTuesday表記がなければ曜日が除去されること
    text = "7月13日（火）にSKHYへ自動切り替え予定。"
    source_text = "SK Hynix listed on July 10. Ticker switches to SKHY on July 13."
    cleaned = strip_unverified_day_of_week(text, source_text=source_text)
    assert "7月13日" in cleaned
    assert "（火）" not in cleaned

    # 2. ソースに曜日（Friday等）の明記がある場合は保持されること
    text2 = "7月10日（金）にナスダックIPOを実施。"
    source2 = "SK Hynix debuted on Nasdaq on Friday, July 10."
    cleaned2 = strip_unverified_day_of_week(text2, source_text=source2)
    assert "7月10日（金）" in cleaned2

    # 3. filter_fact を通した際に曜日表記が原則不記載としてクリーニングされること
    fact_text = "2026年7月13日（火）に切り替わります。"
    res = filter_fact(fact_text)
    assert "7月13日" in res
    assert "（火）" not in res


def test_strip_unrequested_memory_mentions():
    """記憶参照違反防衛：ユーザーの質問にない過去プロジェクト（顔写真保護アプリ等）を結語へ絡めた場合、自動削除すること"""
    from app.core.fact_filter import strip_unrequested_memory_mentions

    raw_text = (
        "推奨アーキテクチャ案としてgpt-oss-20bやOllamaを活用すれば実装可能です。\n\n"
        "Naoが顔写真保護アプリで見せてきたようなモダンなUIデザインを適用できれば差別化できます。"
    )

    # 1. ユーザー入力で過去プロジェクトに触れていない場合は削除されること
    cleaned = strip_unrequested_memory_mentions(raw_text, user_input="オズチャットに似た買い切りアプリ作れるかな？")
    assert "推奨アーキテクチャ案" in cleaned
    assert "顔写真保護アプリ" not in cleaned

    # 2. ユーザーが明示的に言及した場合（「顔写真保護の時みたいに〜」）は保持されること
    cleaned_allowed = strip_unrequested_memory_mentions(raw_text, user_input="顔写真保護アプリの時の経験を生かして作れる？")
    assert "顔写真保護アプリ" in cleaned_allowed


def test_strip_unrequested_yahoo_finance():
    """非金融・一般トレンド質問時に不要なYahoo Finance案内が自動削除されることのテスト"""
    from app.core.fact_filter import strip_unrequested_yahoo_finance

    raw_answer = (
        "欧米ではエコツーリズムやデジタルデトックス旅が注目を集めています。\n\n"
        "📊 最新の市場データについては、Yahoo Finance をご確認ください。"
    )

    # 1. ユーザー入力が非金融質問（「最近欧米のトレンドって何かある？」）の場合は削除されること
    cleaned = strip_unrequested_yahoo_finance(raw_answer, user_input="最近欧米のトレンドって何かある？")
    assert "エコツーリズムやデジタルデトックス旅" in cleaned
    assert "Yahoo Finance" not in cleaned

    # 2. ユーザー入力が株価・銘柄の質問である場合は保持されること
    cleaned_stock = strip_unrequested_yahoo_finance(raw_answer, user_input="AAPLの株価動向教えて")
    assert "Yahoo Finance" in cleaned_stock


def test_strip_outdated_past_event_predictions():
    """時系列ハルシネーション防衛：過去イベントの進行形記述（冬季五輪に向けて等）が是正されることのテスト"""
    from app.core.fact_filter import strip_outdated_past_event_predictions
    raw_text = "ミラノ冬季五輪に向けて航空券の検索数が増加しています。"
    corrected = strip_outdated_past_event_predictions(raw_text)
    assert "冬季五輪に向けて" not in corrected
    assert "冬季五輪（2月開催済み）以降の動向として" in corrected


def test_enforce_variable_numerical_claims_normalization():
    """所要時間・料金情報の過剰置換防止（表記ゆれ許容）テスト"""
    from app.core.fact_filter import enforce_variable_numerical_claims

    source_text = "白浜中央海水浴場から徒歩1分、車で約13分。ランチ丼は大人 2,500円"

    # 1. 所要時間の表記ゆれ（「車13分」「徒歩約1分」等）がソース内の分数と合致すれば保持されること
    text1 = "ホテルから徒歩約1分、シュノーケリングスポットまで車13分です。"
    filtered1 = enforce_variable_numerical_claims(text1, source_text)
    assert "徒歩約1分" in filtered1
    assert "車13分" in filtered1
    assert "要確認" not in filtered1

    # 2. 料金の表記ゆれ（「2500円」「2,500円」等）が合致すれば保持されること
    text2 = "ランチ丼は2500円でお楽しみいただけます。"
    filtered2 = enforce_variable_numerical_claims(text2, source_text)
    assert "2500円" in filtered2


def test_verify_maintenance_date_relevance():
    """工事・休業期間の日付重複検証および誤警報補正テスト"""
    from app.core.fact_filter import verify_maintenance_date_relevance

    user_input = "下田プリンスホテル周辺のおすすめ教えて7/19-7/20家族3人で旅行行くんだよね"
    source_text = "プール施設メンテナンス工事のお知らせ 工事期間：2026年7月13日（月）〜7月15日（水）"

    # 1. 期間が重複していない場合、誤警報が正しい日付関係の説明へ補正されること
    alarm_text = "2026年7月、ホテル公式サイトにてプール施設がメンテナンス工事中と告知されています。プールのご利用はできませんのでご注意ください。"
    corrected = verify_maintenance_date_relevance(alarm_text, source_text=source_text, user_input=user_input)
    assert "影響なくご利用いただける見込みです" in corrected
    assert "7月13日〜7月15日" in corrected

    # 2. 期間が重複している場合（例: 7/13〜7/14に旅行）、元の注意文が維持されること
    overlapping_user_input = "7/13-7/14に旅行に行きます"
    untouched = verify_maintenance_date_relevance(alarm_text, source_text=source_text, user_input=overlapping_user_input)
    assert untouched == alarm_text


def test_1hop_top_or_list_page_detection():
    """1-hop追跡の対象（トップページ・一覧ページ判定）の検証テスト"""
    from urllib.parse import urlparse

    def is_top_or_list(url: str) -> bool:
        parsed_base = urlparse(url)
        path_parts = [p for p in parsed_base.path.strip("/").split("/") if p]
        return (
            len(path_parts) <= 1
            or parsed_base.path in ["", "/", "/index.html", "/index.php"]
            or any(kw in parsed_base.path.lower() for kw in ["news", "info", "notice", "topic", "list"])
        )

    # トップページや一覧ページは True になること
    assert is_top_or_list("https://www.princehotels.co.jp/shimoda/") is True
    assert is_top_or_list("https://www.princehotels.co.jp/shimoda/news/") is True
    assert is_top_or_list("https://www.princehotels.co.jp/shimoda/informations/") is True

    # 個別記事ページ・階層の深いページは False になること
    assert is_top_or_list("https://www.princehotels.co.jp/shimoda/restaurant/menu/detail/12345.html") is False


@pytest.mark.anyio
async def test_jina_deduplication_cache():
    """Jinaおよび直接フェッチにおける同一URL重複リクエストキャッシュ機構のテスト"""
    from app.core.search.providers.jina import _RECENT_FETCH_CACHE, fetch_direct_html
    import time

    test_url = "https://example.com/test_dedup_cache"
    _RECENT_FETCH_CACHE[test_url] = (time.time(), "CACHED_CONTENT_TEST")

    # キャッシュヒットして実際に通信せず CACHED_CONTENT_TEST が返ること
    result = await fetch_direct_html(test_url)
    assert result == "CACHED_CONTENT_TEST"

    # 後始末
    _RECENT_FETCH_CACHE.pop(test_url, None)






