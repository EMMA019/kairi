"""KVメモリ保存・参照ポリシーの単体テスト。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.memory_policy import (
    should_accept_kv_action,
    user_allows_memory_use,
    user_requests_memory_save,
    is_junk_memory,
    entry_matches_user_input,
)
from app.core.fact_filters.format import strip_unrequested_memory_mentions


def test_omakase_is_not_memory_permission():
    assert not user_allows_memory_use("おまかせします")
    assert not user_allows_memory_use("全部おまかせします")
    assert not user_requests_memory_save("おまかせします")
    assert user_allows_memory_use("記憶を使って提案して")
    assert user_requests_memory_save("GOOGLを持ってることを記憶しておいてください")


def test_reject_kv_add_without_explicit_save():
    action = {
        "action": "add",
        "category": "profile",
        "quote": "おまかせします",
        "summary": {"target": "趣味", "note": "競馬・サッカー・猫", "tags": ["競馬"]},
    }
    ok, reason = should_accept_kv_action("おまかせします", action)
    assert not ok
    assert "明示" in reason or "保存" in reason


def test_accept_explicit_googl_save():
    user = "今GOOGLを保有していることを記憶しておいてください！絶賛＄350くらいで取得しててマイナス中（2株だけどねｗ）"
    action = {
        "action": "add",
        "category": "profile",
        "quote": "今GOOGLを保有していることを記憶しておいてください！絶賛＄350くらいで取得しててマイナス中（2株だけどねｗ）",
        "summary": {
            "target": "GOOGL保有状況",
            "note": "2株保有。取得価格約350ドル。",
            "tags": ["GOOGL", "株"],
        },
    }
    ok, reason = should_accept_kv_action(user, action)
    assert ok, reason


def test_reject_soccer_news_as_profile():
    action = {
        "action": "add",
        "category": "profile",
        "quote": "モーガン・ロジャース",
        "summary": {
            "target": "モーガン・ロジャース",
            "note": "アストン・ヴィラからチェルシーへ移籍、移籍金約1億3700万ユーロ",
            "tags": ["サッカー", "移籍"],
        },
    }
    ok, _ = should_accept_kv_action("欧州サッカーのビッグディール教えて", action)
    assert not ok


def test_junk_detects_image_and_transfer_noise():
    assert is_junk_memory({
        "category": "profile",
        "quote": "画像リクエスト",
        "summary": {"target": "画像送信リクエスト", "note": "がぞうおくってー"},
    })
    assert is_junk_memory({
        "category": "profile",
        "quote": "猫を2匹飼ってる",  # demo seed
        "summary": {"target": "猫", "stance": "好き"},
    })
    # 「非保有者」に含まれる「保有」で誤って残さない
    assert is_junk_memory({
        "category": "profile",
        "quote": "マルチプロバイダ利用",
        "summary": {
            "target": "マルチプロバイダ利用",
            "note": "GPU非保有者に推奨",
        },
    })
    # 明示保存の保有銘柄は残す
    assert not is_junk_memory({
        "category": "profile",
        "quote": "今GOOGLを保有していることを記憶しておいてください！",
        "summary": {
            "target": "GOOGL保有状況",
            "note": "2株保有。取得価格約350ドル。",
        },
    })


def test_entry_match_keyword_only():
    entry = {
        "category": "profile",
        "summary": {"target": "GOOGL保有状況", "note": "2株", "tags": ["GOOGL", "株"]},
    }
    assert entry_matches_user_input(entry, "GOOGLどうなった？")
    assert not entry_matches_user_input(entry, "おまかせします。$20で稼げるシステム考えて")


def test_strip_hobby_personalization_violation():
    raw = (
        "$20の予算を最大限活かす構成として、ドメイン取得＋無料ホスティングで"
        "アフィリエイトブログを構築する案を提案します。"
        "Naoさんの趣味（競馬、サッカー、猫など）をテーマにすれば記事作成のモチベーションも維持しやすいと思います。"
    )
    cleaned = strip_unrequested_memory_mentions(raw, user_input="おまかせします")
    assert "ドメイン取得" in cleaned or "$20" in cleaned or "アフィリエイト" in cleaned
    assert "競馬" not in cleaned
    assert "猫" not in cleaned
