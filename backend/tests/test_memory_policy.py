"""KVメモリ保存・参照ポリシーの単体テスト。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.memory_policy import (
    should_accept_kv_action,
    user_allows_memory_use,
    user_requests_memory_save,
    user_requests_forget,
    user_in_holdings_context,
    is_junk_memory,
    entry_matches_user_input,
    targets_are_same_slot,
    entry_has_standing_grant,
    entry_in_standing_grant_scope,
    standing_grant_allows_use,
    family_occasion_allows_use,
    family_topic_allows_use,
    infer_family_tag,
    user_in_family_occasion_context,
    user_in_family_topic_context,
    user_in_family_travel_context,
    find_entry_for_memory_edit,
    merge_memory_note,
    resolve_kv_mutation,
    should_edit_existing_memory,
    FAMILY_TAG_CHILD,
    FAMILY_TAG_SPOUSE,
)
from app.core.chat_orchestrator import build_executor_instruction
from app.core.chat_orchestrator import resolve_memory_inject
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


def test_junk_detects_compressor_ephemeral_market_facts():
    """会話圧縮由来の一時タグ・市場エフェメラルは junk。"""
    assert is_junk_memory({
        "category": "profile",
        "quote": "日経平均",
        "summary": {
            "target": "日経平均",
            "note": "前場終値61,689.86円（前日比-675.06円）",
            "tags": ["一時データ", "スキャン結果"],
        },
    })
    assert is_junk_memory({
        "category": "profile",
        "quote": "日銀政策",
        "summary": {
            "target": "日銀政策",
            "note": "追加利上げ観測、7/31会合が注目点",
            "tags": [],
        },
    })
    assert is_junk_memory({
        "category": "profile",
        "quote": "今後の注目イベント",
        "summary": {
            "target": "今後の注目イベント",
            "note": "7/29 Microsoft決算、7/31 日銀会合",
        },
    })
    # 明示保存の保有は tags がなくても残す
    assert not is_junk_memory({
        "category": "profile",
        "quote": "今GOOGLを保有していることを記憶しておいてください！絶賛＄350くらいで取得しててマイナス中（2株だけどねｗ）",
        "summary": {
            "target": "GOOGL保有状況",
            "note": "GOOGL（アルファベット株式）を2株保有。取得価格約350ドル。",
        },
    })


def test_entry_match_keyword_only():
    entry = {
        "category": "profile",
        "summary": {"target": "GOOGL保有状況", "note": "2株", "tags": ["GOOGL", "株"]},
    }
    assert entry_matches_user_input(entry, "GOOGLどうなった？")
    assert not entry_matches_user_input(entry, "おまかせします。$20で稼げるシステム考えて")


def test_ascii_ticker_not_substring_of_company_name():
    """ティッカーが社名の部分文字列でも誤マッチしない（全銘柄共通・単語境界）。"""
    # googl ⊆ google 型
    googl = {
        "category": "profile",
        "summary": {"target": "GOOGL保有状況", "note": "2株保有", "tags": ["GOOGL", "株"]},
    }
    assert not entry_matches_user_input(
        googl, "Google健闘してるんだけどいいニュースとかあった？"
    )
    assert entry_matches_user_input(googl, "GOOGLの含みどう？")
    # 社名エイリアス表は持たないので、ティッカー未言及の社名＋保有だけではマッチしない
    assert not entry_matches_user_input(googl, "グーグル保有どうなってる？")

    cat = {
        "category": "profile",
        "summary": {"target": "CAT保有", "note": "建機", "tags": ["CAT"]},
    }
    assert not entry_matches_user_input(cat, "education sector outlook news")
    assert entry_matches_user_input(cat, "CATの保有どうなってる？")


def test_resolve_memory_inject_blocks_news_personalization():
    """社名ニュースだけでは保有KVを Executor に渡さない（銘柄非依存ゲート）。"""
    kv = "- MSFT保有状況: 2株 / 取得約350ドル"
    sj, injected = resolve_memory_inject(
        {"memory_inject": True},
        kv,
        user_input="Microsoft健闘してるんだけどいいニュースとかあった？",
    )
    assert sj["memory_inject"] is False
    assert injected is None

    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        kv,
        user_input="MSFTの含み損どう？",
    )
    assert sj2["memory_inject"] is True
    assert injected2 == kv

    sj3, injected3 = resolve_memory_inject(
        {"memory_inject": True},
        kv,
        user_input="記憶を使って提案して",
    )
    assert sj3["memory_inject"] is True
    assert injected3 == kv


def test_holdings_context_helper():
    assert user_in_holdings_context("MSFTの含みどう？")
    assert not user_in_holdings_context("Microsoftのいいニュースあった？")


_CHILD_KV = {
    "category": "profile",
    "quote": "子ども　emma　女　2019/11/13　※私が今後の会話で子どもに触れたら記憶使っていいよ　覚えておいて",
    "summary": {
        "target": "子ども（emma）の生年月日・性別",
        "note": "2019年11月13日生まれ、女性。今後の会話で子どもに触れた場合の記憶利用はユーザー本人から許可済み。",
        "tags": ["emma", "子ども"],
    },
}


def test_child_standing_grant_scope():
    assert entry_has_standing_grant(_CHILD_KV)
    assert entry_in_standing_grant_scope(_CHILD_KV, "emmaの誕生日いつ？")
    assert entry_in_standing_grant_scope(_CHILD_KV, "子供向けのレストラン教えて")
    assert entry_in_standing_grant_scope(_CHILD_KV, "子どもと行ける店")
    assert not entry_in_standing_grant_scope(_CHILD_KV, "今日の天気は？")
    assert not entry_in_standing_grant_scope(_CHILD_KV, "Microsoftのいいニュースあった？")


def test_standing_grant_injects_without_per_turn_phrase():
    kv = (
        "- [PROFILE] 子ども（emma）の生年月日・性別: 2019年11月13日生まれ、女性。"
        "今後の会話で子どもに触れた場合の記憶利用はユーザー本人から許可済み。"
    )
    assert standing_grant_allows_use("子供の誕生日いつだっけ", kv)
    assert standing_grant_allows_use("emmaに合うプレゼント", kv)
    assert not standing_grant_allows_use("今日の天気は？", kv)
    assert not user_allows_memory_use("子供の誕生日いつだっけ")

    sj, injected = resolve_memory_inject(
        {"memory_inject": False},
        kv,
        user_input="子供向けのランチある？",
    )
    assert sj["memory_inject"] is True
    assert injected == kv

    wife_kv = "- [PROFILE] 妻saoriの生年月日: 1989年12月29日生まれ。Naoの妻。"
    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        wife_kv,
        user_input="今日の天気は？",
    )
    assert sj2["memory_inject"] is False
    assert injected2 is None


def test_wife_birthday_gift_uses_profile():
    """妻の誕生日×プレゼントは、継続許可なしでも妻プロフィールを使ってよい。"""
    user = "妻の誕生日近いんだけど、プレゼント何がいいかな？"
    assert user_in_family_occasion_context(user)
    assert not user_allows_memory_use(user)

    wife_kv = "- [PROFILE] 妻saoriの生年月日: 1989年12月29日生まれ。Naoの妻。"
    assert family_occasion_allows_use(user, wife_kv)
    assert not family_occasion_allows_use("プレゼント何がいいかな？", wife_kv)

    yogurt_kv = "- [PREFERENCE] 好きな食べ物 (好き): ヨーグルト"
    assert not family_occasion_allows_use(user, yogurt_kv)
    assert family_topic_allows_use("妻とご飯行きたい", wife_kv)

    sj, injected = resolve_memory_inject(
        {"memory_inject": False},
        wife_kv,
        user_input=user,
    )
    assert sj["memory_inject"] is True
    assert injected == wife_kv

    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        wife_kv,
        user_input="妻と喧嘩した",
    )
    assert sj2["memory_inject"] is True
    assert injected2 == wife_kv


def test_accept_oboeteite_profile_save():
    """回帰: 「覚えていてほしいこと…」は明示的保存指示として受理する（2026-08 保存不能バグ）。"""
    user = (
        "覚えていてほしいこと①1988/10/19生まれ②好きな食べ物カレー"
        "③好きな飲み物ジン④こども2019/11/13生まれの女の子でバレエ習ってる"
    )
    action = {
        "action": "add",
        "category": "profile",
        "quote": user,
        "summary": {
            "target": "ユーザープロフィール",
            "note": "誕生日: 1988/10/19 / 好きな食べ物: カレー / 好きな飲み物: ジン / 子供: 2019/11/13生まれの女の子・バレエ習い中",
            "tags": ["誕生日", "カレー", "ジン", "子供", "バレエ"],
        },
    }
    ok, reason = should_accept_kv_action(user, action)
    assert ok, reason


def test_save_pattern_variants_accepted():
    """「覚えていてほしい/覚えてほしい/覚えてね/記憶してほしい」系の自然な保存依頼を受理。"""
    assert user_requests_memory_save("私の誕生日を覚えていてほしい")
    assert user_requests_memory_save("この内容を覚えてほしい")
    assert user_requests_memory_save("カレーが好きって覚えてね")
    assert user_requests_memory_save("次の予定を記憶してほしい")
    assert user_requests_memory_save("覚えててください")
    assert user_requests_memory_save("メモリへの追加①3人家族")
    assert user_requests_memory_save("私1988/10/19生まれメモリへ追加")
    assert user_requests_memory_save("3人家族ってメモリに追加")
    assert user_requests_memory_save("家族構成を記憶に追加して")


def test_non_save_utterances_still_rejected():
    """保存指示でない発言は従来どおり拒否（誤保存防止を維持）。"""
    assert not user_requests_memory_save("おまかせします")
    assert not user_requests_memory_save("おはよう")
    assert not user_requests_memory_save("カレーの写真を見せて")
    assert not user_requests_memory_save("覚えてる?")
    assert not user_requests_memory_save("今日の米国市場どうだった？")


def test_strip_hobby_personalization_violation():
    raw = (
        "$20の予算を最大限活かす構成として、ドメイン取得＋無料ホスティングで"
        "アフィリエイトブログを構築する案を提案します。"
        "Alexさんの趣味（競馬、サッカー、猫など）をテーマにすれば記事作成のモチベーションも維持しやすいと思います。"
    )
    cleaned = strip_unrequested_memory_mentions(raw, user_input="おまかせします")
    assert "ドメイン取得" in cleaned or "$20" in cleaned or "アフィリエイト" in cleaned
    assert "競馬" not in cleaned
    assert "猫" not in cleaned


def test_accept_memory_he_tsuika_family():
    """回帰: 「メモリへの追加①3人家族」は quote が短くても保存する。"""
    user = "メモリへの追加①3人家族"
    action = {
        "action": "add",
        "category": "profile",
        "quote": "3人家族",
        "summary": {"target": "3人家族", "note": "家族構成は3人", "tags": ["家族"]},
    }
    ok, reason = should_accept_kv_action(user, action)
    assert ok, reason


def test_accept_memory_he_tsuika_birthday():
    user = "私1988/10/19生まれメモリへ追加"
    action = {
        "action": "add",
        "category": "profile",
        "quote": "私1988/10/19生まれメモリへ追加",
        "summary": {
            "target": "生年月日",
            "note": "1988年10月19日生まれ",
            "tags": ["誕生日"],
        },
    }
    ok, reason = should_accept_kv_action(user, action)
    assert ok, reason


def test_profile_slots_do_not_collapse_family_birthdays():
    """妻の生年月日は本人の生年月日と同一スロットにしない。"""
    assert not targets_are_same_slot("生年月日", "妻の生年月日")
    assert not targets_are_same_slot("誕生日", "妻の誕生日")
    assert not targets_are_same_slot("家族", "3人家族")
    assert targets_are_same_slot("生年月日", "生年月日")
    assert targets_are_same_slot("GOOGL保有", "GOOGL保有状況")
    assert targets_are_same_slot("GOOGL保有状況", "GOOGL保有")


def test_rejected_kv_instruction_forbids_false_confirm():
    text = build_executor_instruction({
        "instruction": {
            "facts_to_present": ["3人家族をメモリに追加した"],
            "logical_order": ["確認する"],
        },
        "kv_action": {"action": "none", "rejected_reason": "明示的な保存指示がない（おまかせ等は不可）"},
    })
    assert "保存されませんでした" in text
    assert "成功表現は禁止" in text
    assert "3人家族をメモリに追加した" not in text


_WIFE_KV = {
    "category": "profile",
    "quote": "妻　saori　1989/12/29　覚えておいて",
    "summary": {
        "target": "妻saoriの生年月日",
        "note": "1989年12月29日生まれ。Naoの妻。",
        "tags": [],
    },
}
_SELF_KV = {
    "category": "profile",
    "quote": "私1988/10/19　男　覚えておいて",
    "summary": {
        "target": "Naoの生年月日・性別",
        "note": "1988年10月19日生まれ、男性",
        "tags": [],
    },
}
_YOGURT_KV = {
    "category": "preference",
    "quote": "私の好きな食べ物はヨーグルトって覚えておいて",
    "summary": {"target": "好きな食べ物", "stance": "好き", "note": "ヨーグルト", "tags": []},
}


def test_infer_family_tag_spouse_child_not_self():
    assert infer_family_tag(_WIFE_KV) == FAMILY_TAG_SPOUSE
    assert infer_family_tag(_CHILD_KV) == FAMILY_TAG_CHILD
    assert infer_family_tag(_SELF_KV) is None
    assert infer_family_tag(_YOGURT_KV) is None


def test_family_travel_uses_flagged_slots_only():
    user = "家族で旅行に行くんだけど"
    assert user_in_family_travel_context(user)
    assert not user_in_family_travel_context("旅の相談して")
    assert not user_in_family_travel_context("旅行行きたい")
    assert not user_in_family_travel_context("家族の話")

    wife_text = "- [PROFILE] 妻saoriの生年月日: 1989年12月29日生まれ。Naoの妻。"
    child_text = "- [PROFILE] 子ども（emma）の生年月日・性別: 2019年11月13日生まれ、女性。"
    yogurt_text = "- [PREFERENCE] 好きな食べ物 (好き): ヨーグルト"
    self_text = "- [PROFILE] Naoの生年月日・性別: 1988年10月19日生まれ、男性"

    assert family_topic_allows_use(user, wife_text + "\n" + child_text)
    assert not family_topic_allows_use(user, yogurt_text)
    assert not family_topic_allows_use(user, self_text)
    assert not family_topic_allows_use("旅の相談して", wife_text + "\n" + child_text)
    assert not family_topic_allows_use("旅行行きたい", child_text)

    sj, injected = resolve_memory_inject(
        {"memory_inject": False},
        wife_text + "\n" + child_text,
        user_input=user,
    )
    assert sj["memory_inject"] is True
    assert injected is not None

    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        child_text,
        user_input="旅の相談して",
    )
    assert sj2["memory_inject"] is False
    assert injected2 is None


def test_news_and_omakase_do_not_use_family_flags():
    child_text = "- [PROFILE] 子ども（emma）の生年月日・性別: 2019年11月13日生まれ。"
    sj, injected = resolve_memory_inject(
        {"memory_inject": True},
        child_text,
        user_input="Microsoftのいいニュースあった？",
    )
    assert sj["memory_inject"] is False
    assert injected is None

    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        child_text,
        user_input="おまかせでアプリ作って",
    )
    assert sj2["memory_inject"] is False
    assert injected2 is None


def test_append_emma_food_updates_child_not_yogurt():
    user = "emmaの記憶にパスタ（バジル系）とピザが好きって追記で覚えておいて"
    assert user_requests_memory_save(user)
    assert should_edit_existing_memory(user)

    child = {**_CHILD_KV, "id": 3}
    wife = {**_WIFE_KV, "id": 2}
    yogurt = {**_YOGURT_KV, "id": 4}
    self_row = {**_SELF_KV, "id": 1}
    found = find_entry_for_memory_edit(user, [self_row, wife, child, yogurt])
    assert found is not None
    assert found["id"] == 3

    action = {
        "action": "add",
        "category": "preference",
        "quote": "パスタ（バジル系）とピザが好きって追記で覚えておいて",
        "summary": {
            "target": "好きな食べ物",
            "stance": "好き",
            "note": "パスタ（バジル系）・ピザが好き",
            "tags": ["パスタ", "ピザ"],
        },
    }
    ok, reason = should_accept_kv_action(user, action)
    assert ok, reason

    resolved = resolve_kv_mutation(user, action, [self_row, wife, child, yogurt])
    assert resolved is not None
    act, payload, tid = resolved
    assert act == "update"
    assert tid == 3
    note = payload["summary"]["note"]
    assert "2019年11月13日" in note
    assert "パスタ" in note
    assert payload["summary"]["target"] == child["summary"]["target"]
    assert payload["quote"] == child["quote"]


def test_merge_memory_note_appends_once():
    old = "2019年11月13日生まれ、女性。"
    new = "パスタ（バジル系）・ピザが好き"
    merged = merge_memory_note(old, new)
    assert "2019年11月13日" in merged
    assert "パスタ" in merged
    assert merge_memory_note(merged, new) == merged


def test_update_without_target_still_resolves_by_name():
    user = "emmaのプロフィールにピザ好きを追記して"
    child = {**_CHILD_KV, "id": 9}
    resolved = resolve_kv_mutation(
        user,
        {
            "action": "update",
            "summary": {"note": "ピザが好き"},
        },
        [child],
    )
    assert resolved is not None
    assert resolved[0] == "update"
    assert resolved[2] == 9


def test_strip_child_ask_on_event_query_keeps_child_subject():
    from app.core.fact_filters.format import strip_unrequested_child_ask

    event = "今日埼玉か東京でイベント的なのあるかな？"
    leaked = (
        "埼玉の花火大会があります。\n"
        "ちなみに今回はお車と電車どちらでしょう？お子様の年齢に合わせて最適なプランに調整できますので、もしよろしければお知らせくださいね。"
    )
    cleaned = strip_unrequested_child_ask(leaked, event)
    assert "お子様の年齢" not in cleaned
    assert "花火大会" in cleaned

    with_child = (
        "6歳のemmaちゃんとお二人ですね。お子様の年齢に合わせて昆虫展がよいです。"
    )
    kept = strip_unrequested_child_ask(with_child, "妻が出かけてて子どもと2人なんだよねえ")
    assert "emma" in kept
    assert "昆虫展" in kept


def test_english_memory_use_and_save_phrases():
    assert user_allows_memory_use("use my memory for this")
    assert user_allows_memory_use("based on what you remember")
    assert not user_allows_memory_use("I remember seeing that festival last year")
    assert not user_requests_memory_save("I remember seeing that festival last year")
    assert user_requests_memory_save("remember this: I like curry")
    assert user_requests_memory_save("add to memory that we are a family of three")
    assert user_requests_memory_save("save this to memory")
    assert user_requests_forget("forget that")
    assert user_requests_forget("delete that from memory")
    assert should_edit_existing_memory("append pasta to emma's memory")
    assert should_edit_existing_memory("add to emma's memory that she likes pizza")
    assert should_edit_existing_memory("update her profile with pizza")


def test_english_family_topic_matches_japanese_contract():
    assert user_in_family_topic_context("Do you have any recommendations for kids?")
    assert not user_in_family_topic_context("Is there an event in Saitama or Tokyo today?")
    assert not user_in_family_topic_context("kidney specialist nearby")
    assert not user_in_family_topic_context("ask the midwife")

    assert user_in_family_travel_context("planning a family trip")
    assert user_in_family_travel_context("traveling with family")
    assert not user_in_family_travel_context("just travel advice")
    assert not user_in_family_travel_context("family conversation")

    wife_kv = "- [PROFILE] 妻saoriの生年月日: 1989年12月29日生まれ。Naoの妻。"
    child_kv = "- [PROFILE] 子ども（emma）の生年月日・性別: 2019年11月13日生まれ、女性。"
    assert family_topic_allows_use("wife's birthday gift ideas", wife_kv)
    assert family_topic_allows_use("Do you have any recommendations for kids?", child_kv)
    assert family_topic_allows_use("family trip this weekend", wife_kv + "\n" + child_kv)
    assert not family_topic_allows_use("just travel advice", child_kv)
    assert not family_topic_allows_use("Is there an event in Saitama or Tokyo today?", child_kv)

    sj, injected = resolve_memory_inject(
        {"memory_inject": False},
        child_kv,
        user_input="Do you have any recommendations for kids?",
    )
    assert sj["memory_inject"] is True
    assert injected == child_kv

    sj2, injected2 = resolve_memory_inject(
        {"memory_inject": True},
        child_kv,
        user_input="Is there an event in Saitama or Tokyo today?",
    )
    assert sj2["memory_inject"] is False
    assert injected2 is None


def test_english_standing_grant_and_holdings():
    assert entry_in_standing_grant_scope(_CHILD_KV, "recommendations for kids")
    assert standing_grant_allows_use("kids events today", (
        "- [PROFILE] 子ども（emma）の生年月日・性別: 2019年11月13日生まれ。"
        "今後の会話で子どもに触れた場合の記憶利用はユーザー本人から許可済み。"
    ))
    en_grant = {
        "category": "profile",
        "quote": "when I mention my kid you can use memory",
        "summary": {
            "target": "child (emma)",
            "note": "you can use memory when I talk about kids",
            "tags": ["emma", "child"],
        },
    }
    assert entry_has_standing_grant(en_grant)
    assert entry_in_standing_grant_scope(en_grant, "kids events today")
    assert not entry_in_standing_grant_scope(en_grant, "Is there an event in Saitama today?")

    assert user_in_holdings_context("how is my portfolio today?")
    assert user_in_holdings_context("check my holdings")
    assert not user_in_holdings_context("any good Microsoft news?")


def test_english_infer_family_tag_and_child_ask_strip():
    from app.core.fact_filters.format import strip_unrequested_child_ask

    en_child = {
        "category": "profile",
        "quote": "my child emma remember this",
        "summary": {"target": "child emma", "note": "born 2019", "tags": ["emma"]},
    }
    en_wife = {
        "category": "profile",
        "quote": "my wife saori remember this",
        "summary": {"target": "wife saori", "note": "birthday in December", "tags": ["saori"]},
    }
    assert infer_family_tag(en_child) == FAMILY_TAG_CHILD
    assert infer_family_tag(en_wife) == FAMILY_TAG_SPOUSE

    leaked = (
        "There are fireworks in Saitama. "
        "How old is your child? I can tailor the plan."
    )
    cleaned = strip_unrequested_child_ask(
        leaked, "Is there an event in Saitama or Tokyo today?"
    )
    assert "How old is your child" not in cleaned
    assert "fireworks" in cleaned

    kept = strip_unrequested_child_ask(
        "For a 6-year-old, the insect walk is a good kids pick.",
        "Do you have any recommendations for kids?",
    )
    assert "insect walk" in kept
    assert "6-year-old" in kept
