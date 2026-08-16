"""
KVメモリの保存・参照ポリシー（「記憶を勝手に使わない」の機械ゲート）

プロンプトだけの注意書きでは DeepSeek が無視するため、ここを正としてコード側で拒否する。
"""
from __future__ import annotations

import re
from typing import Any, Optional

# 明示的な「記憶を使ってよい」指示
_MEMORY_USE_PATTERNS = [
    r"記憶を使",
    r"記憶を参照",
    r"記憶に基づ",
    r"過去の相談を踏ま",
    r"過去の(?:話|相談|会話|プロジェクト)を",
    r"前の(?:話|相談|約束)を踏ま",
    r"覚えてる[？?]?",
    r"覚えてますか",
    r"覚えてるかな",
    r"前に話した",
    r"以前(?:話|相談)した",
    r"私の(?:好み|趣味|プロフィール|好みに合わせ)",
    r"俺の(?:好み|趣味)",
    r"僕の(?:好み|趣味)",
    r"KVメモリ",
    r"長期記憶",
    r"\buse (?:my |the )?memory\b",
    r"\bbased on (?:my )?(?:profile|what you remember)\b",
    r"\bwhat you remember about me\b",
    r"(?:do you|you) remember (?:me|my|what)\b",
]

# 明示的な「保存して」指示
_MEMORY_SAVE_PATTERNS = [
    r"覚えておいて",
    r"覚えといて",
    r"覚えていて",  # 覚えていてほしい/ください/ね を包含
    r"覚えてほしい",
    r"覚えてね",
    r"覚えてて",
    r"記憶しておいて",
    r"記憶して(?:ください|くれ|て|ほしい)",
    r"メモして",
    r"メモっといて",
    r"記録して",
    r"忘れないで",
    r"忘れんといて",
    r"メモリへ(?:の)?追加",
    r"メモリに追加",
    r"記憶に追加",
    r"追記",
    r"remember\s+(?:this|that|it)",
    r"please\s+remember",
    r"\badd (?:this |it )?to memory\b",
    r"\bsave (?:this|that)(?: to memory)?\b",
    r"\bdon't forget\b",
    r"\bdo not forget\b",
]

# ペルソナ変更（カテゴリ persona のみ許可）
_PERSONA_PATTERNS = [
    r"ギャルモード",
    r"関西弁にして",
    r"子供口調",
    r"ペルソナ",
    r"口調にして",
    r"モードにして",
    r"モードON",
    r"アナリストモード",
]

# 忘却・除外
_FORGET_PATTERNS = [
    r"忘れて",
    r"忘れろ",
    r"記憶から消",
    r"記憶を消",
    r"削除して",
    r"もう覚えないで",
    r"\bforget (?:that|this|it)\b",
    r"\bdelete (?:that |this )?from memory\b",
    r"\bremove (?:that |this )?from memory\b",
]

# 会話メタ・ニュース・AI自己紹介など「ユーザーの長期特徴」ではないゴミ
_JUNK_TARGET_RE = re.compile(
    r"("
    r"画像|写真|selfie|リクエスト|エラー|API|"
    r"移籍|サッカー|プレミア|トッテナム|チェルシー|リバプール|"
    r"マンチェスター|日本人選手|カルパナ|キングジョージ|競馬|"
    r"アシスタント|キャラクター|カイリ|かいり|応答|会話の流れ|"
    r"ソース|出典|検索結果|ニュース|ディール|"
    r"本日の|今日の食事|夕飯|カレーの写真|海の写真|学校の写真|"
    r"過去の話題|ユーザーの反応|動作背景|運用状況|"
    r"Morph|DeepSeek|MiniMAX|GLM-|Gemini|OpenRouter|Kimi|マルチプロバイダ|"
    r"開発依頼|方向性|現状|参考ソース|収益化|意図変更|投資手段|"
    r"ジタン|ゴロワーズ|Gitanes|アルファベット株|"
    # 市場・指標のエフェメラル要約（圧縮/会話由来）
    r"日経|TOPIX|前場|後場|終値|始値|業種|セクター|半導体|"
    r"銀行セクター|金融セクター|FOMC|日銀|金融政策|"
    r"Microsoft決算|MSFT決算|SKハイニックス|原油|為替・金利|"
    r"支援材料|懸念材料|今後の注目|注目イベント|"
    # 会話メタ・未完了タスクメモ
    r"ユーザーの追加質問|未回答|最終指示|改善方針|改善点|"
    r"ユーザー最終要求|ユーザーからのフィードバック|実運用に向けた方向性|"
    r"ペアトレード|改良(?:版)?コード|学術リソース"
    r")",
    re.IGNORECASE,
)

_EPHEMERAL_KV_TAGS = {"一時データ", "スキャン結果"}

# quote がユーザー発言の引用でないとき（AIが要約を quote にしている）
_QUOTE_IS_META_RE = re.compile(
    r"^(ユーザー|アシスタント|AI|カイリ|過去の|画像|会話)",
)


def user_allows_memory_use(user_input: str) -> bool:
    """明示的に記憶参照を許可したか。『おまかせ』は許可にならない。"""
    text = (user_input or "").strip()
    if not text:
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in _MEMORY_USE_PATTERNS)


# 保有・ポジション文脈（ニュース質問だけでは inject しない）
_HOLDINGS_CONTEXT_RE = re.compile(
    r"保有|ポジション|含み|取得価|何株|自分の銘柄|ポートフォリオ|持ってる株|持株|"
    r"\bholdings?\b|\bportfolio\b|\bmy shares\b|\bmy position\b",
    re.IGNORECASE,
)


def user_in_holdings_context(user_input: str) -> bool:
    """保有・ポジション・含み損など、プロファイル注入が妥当な発話か。"""
    return bool(_HOLDINGS_CONTEXT_RE.search(user_input or ""))


# エントリに残した「この話題では記憶を使ってよい」許可（今の発話の「記憶を使って」ではない）
_STANDING_GRANT_RE = re.compile(
    r"(?:触れ(?:たら|た場合|たらば)|出たら|言及).{0,24}記憶"
    r"|記憶使って(?:いい|良い|OK|おk)"
    r"|記憶を使って(?:いい|良い)"
    r"|記憶利用.{0,16}許可"
    r"|when I (?:mention|talk about).{0,24}(?:kids?|child|children|wife).{0,24}memory"
    r"|you can use memory when"
    r"|(?:mention|talk about).{0,24}(?:kids?|child|children).{0,32}(?:use memory|memory.{0,16}ok)",
    re.IGNORECASE,
)
_CHILD_SCOPE_RE = re.compile(
    r"子ども|子供|こども|お子様|娘|息子|"
    r"\bkids?\b|\bchildren\b|\bchild\b|\bdaughter\b|\bson\b",
    re.IGNORECASE,
)


def entry_has_standing_grant(entry: dict) -> bool:
    """quote/note に継続的な記憶利用許可があるか。"""
    summary = entry.get("summary") or {}
    blob = f"{entry.get('quote') or ''}\n{summary.get('note') or ''}"
    return bool(_STANDING_GRANT_RE.search(blob))


def entry_in_standing_grant_scope(entry: dict, user_input: str) -> bool:
    """許可済みエントリのスコープ（子ども/名前）に今の発話が触れているか。"""
    if not entry_has_standing_grant(entry):
        return False
    text = (user_input or "").strip()
    if not text:
        return False
    if entry_matches_user_input(entry, text):
        return True
    summary = entry.get("summary") or {}
    tags = summary.get("tags") or []
    blob = " ".join(
        [
            str(summary.get("target") or ""),
            str(summary.get("note") or ""),
            str(entry.get("quote") or ""),
            " ".join(str(t) for t in tags),
        ]
    )
    if _CHILD_SCOPE_RE.search(blob) and _CHILD_SCOPE_RE.search(text):
        return True
    text_lower = text.lower()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{1,15}", blob):
        if _ascii_token_in_text(m.group(0), text_lower):
            return True
    return False


def standing_grant_allows_use(user_input: str, kv_text: str = "") -> bool:
    """スコープ付きKV文面に継続許可があり、今の発話がそのスコープに触れているか。"""
    text = (user_input or "").strip()
    blob = kv_text or ""
    if not text or not blob or not _STANDING_GRANT_RE.search(blob):
        return False
    if _CHILD_SCOPE_RE.search(blob) and _CHILD_SCOPE_RE.search(text):
        return True
    text_lower = text.lower()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{1,15}", blob):
        if _ascii_token_in_text(m.group(0), text_lower):
            return True
    return False


FAMILY_TAG_SPOUSE = "family:spouse"
FAMILY_TAG_CHILD = "family:child"
FAMILY_TAGS = frozenset({FAMILY_TAG_SPOUSE, FAMILY_TAG_CHILD})

_SPOUSE_RE = re.compile(
    r"妻|嫁|奥さん|家内|配偶者|\bwife\b|\bspouse\b",
    re.IGNORECASE,
)
_CHILD_MEMBER_RE = re.compile(
    r"子ども|子供|こども|お子様|娘|息子|"
    r"\bkids?\b|\bchildren\b|\bchild\b|\bdaughter\b|\bson\b",
    re.IGNORECASE,
)
_FAMILY_SLOT_RE = re.compile(
    r"妻|嫁|奥さん|家内|配偶者|夫|主人|旦那|パートナー|"
    r"子ども|子供|こども|お子様|娘|息子|"
    r"\bwife\b|\bspouse\b|\bhusband\b|\bpartner\b|"
    r"\bkids?\b|\bchildren\b|\bchild\b|\bdaughter\b|\bson\b",
    re.IGNORECASE,
)
_FAMILY_TRAVEL_RE = re.compile(
    r"旅行|お出かけ|観光|宿|ホテル|"
    r"\btrip\b|\btravell?ing\b|\btravel\b|\bouting\b|\bhotel\b|\bsightseeing\b",
    re.IGNORECASE,
)
_NEWS_DENY_RE = re.compile(
    r"ニュース|市況|決算|相場|ヘッドライン|"
    r"\bnews\b|\bmarkets?\b|\bearnings\b|\bheadlines?\b",
    re.IGNORECASE,
)
_FAMILY_ALIAS_GROUPS = (
    ("妻", "嫁", "奥さん", "家内", "配偶者", "wife", "spouse"),
    ("夫", "主人", "旦那", "husband"),
    (
        "子ども",
        "子供",
        "こども",
        "お子様",
        "娘",
        "息子",
        "kid",
        "kids",
        "child",
        "children",
        "daughter",
        "son",
    ),
)
_FAMILY_WORD_RE = re.compile(r"家族|\bfamily\b", re.IGNORECASE)
_FAMILY_KV_RE = re.compile(
    r"family:(?:spouse|child)|妻|子ども|子供|お子様|"
    r"\bwife\b|\bspouse\b|\bkids?\b|\bchildren\b|\bchild\b",
    re.IGNORECASE,
)


def _entry_blob(entry: dict) -> str:
    summary = entry.get("summary") or {}
    tags = summary.get("tags") or []
    return " ".join(
        [
            str(summary.get("target") or ""),
            str(summary.get("note") or ""),
            str(entry.get("quote") or ""),
            " ".join(str(t) for t in tags),
        ]
    )


def infer_family_tag(entry: dict) -> str | None:
    """本人・好みには付けない。妻語なら spouse、子ども語なら child。"""
    blob = _entry_blob(entry)
    if _CHILD_MEMBER_RE.search(blob):
        return FAMILY_TAG_CHILD
    if _SPOUSE_RE.search(blob):
        return FAMILY_TAG_SPOUSE
    return None


def entry_family_tag(entry: dict) -> str | None:
    tags = (entry.get("summary") or {}).get("tags") or []
    for tag in tags:
        if tag in FAMILY_TAGS:
            return str(tag)
    return infer_family_tag(entry)


def apply_family_tag(entry: dict) -> dict:
    """tags に family:spouse / family:child を補完する（本人は触らない）。"""
    tag = infer_family_tag(entry)
    if not tag:
        return entry
    summary = entry.setdefault("summary", {})
    tags = list(summary.get("tags") or [])
    if tag not in tags:
        tags.append(tag)
        summary["tags"] = tags
    return entry


def memory_personalization_denied(user_input: str) -> bool:
    """ニュース・おまかせ開発では家族フラグも使わない。"""
    from app.core.omakase_policy import is_omakase_dev_request

    text = user_input or ""
    if is_omakase_dev_request(text):
        return True
    return bool(_NEWS_DENY_RE.search(text))


def user_in_family_travel_context(user_input: str) -> bool:
    """家族 × 旅行/お出かけ。『家族』や『旅の相談』だけでは不可。"""
    text = user_input or ""
    if not _FAMILY_WORD_RE.search(text):
        return False
    return bool(_FAMILY_TRAVEL_RE.search(text))


def user_in_family_topic_context(user_input: str) -> bool:
    """妻/子どもが主語、または家族旅行。ニュース等は不可。"""
    if memory_personalization_denied(user_input):
        return False
    text = user_input or ""
    if user_in_family_travel_context(text):
        return True
    return bool(_FAMILY_SLOT_RE.search(text))


def user_in_family_occasion_context(user_input: str) -> bool:
    """後方互換。話題ゲートは記念日必須ではない。"""
    return user_in_family_topic_context(user_input)


def _family_slot_aliases_hit(text: str, blob: str) -> bool:
    slots = _FAMILY_SLOT_RE.findall(text or "")
    if not slots or not blob:
        return False
    blob_l = blob.lower()
    for slot in slots:
        slot_l = slot.lower()
        group = next(
            (g for g in _FAMILY_ALIAS_GROUPS if slot_l in {a.lower() for a in g}),
            (slot,),
        )
        if any(alias.lower() in blob_l if alias.isascii() else alias in blob for alias in group):
            return True
    return False


def entry_matches_family_slot(entry: dict, user_input: str) -> bool:
    """発話がこの行の家族フラグ（またはスロット語/名前）に触れているか。"""
    if memory_personalization_denied(user_input):
        return False
    tag = entry_family_tag(entry)
    if not tag:
        return False
    if user_in_family_travel_context(user_input):
        return tag in FAMILY_TAGS
    if tag == FAMILY_TAG_SPOUSE and (_SPOUSE_RE.search(user_input or "") or _family_slot_aliases_hit(user_input, _entry_blob(entry))):
        return True
    if tag == FAMILY_TAG_CHILD and (
        _CHILD_MEMBER_RE.search(user_input or "") or _family_slot_aliases_hit(user_input, _entry_blob(entry))
    ):
        return True
    text_lower = (user_input or "").lower()
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{1,15}", _entry_blob(entry)):
        if _ascii_token_in_text(m.group(0), text_lower):
            return True
    return False


def family_topic_allows_use(user_input: str, kv_text: str = "") -> bool:
    """家族話題または家族旅行で、スコープ済みKVがそのスロットを含むときだけ許可。"""
    if not user_in_family_topic_context(user_input) or not (kv_text or "").strip():
        return False
    family_kv = bool(_FAMILY_KV_RE.search(kv_text))
    if user_in_family_travel_context(user_input):
        return family_kv
    return _family_slot_aliases_hit(user_input, kv_text) or (
        family_kv and bool(_FAMILY_SLOT_RE.search(user_input or ""))
    )


def family_occasion_allows_use(user_input: str, kv_text: str = "") -> bool:
    """後方互換。"""
    return family_topic_allows_use(user_input, kv_text)


def _is_ascii_ticker_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9._^]{0,11}", token or ""))


def _ascii_token_in_text(token: str, text_lower: str) -> bool:
    """ASCII トークンは単語境界で照合（googl ⊆ google を防ぐ）。"""
    if not _is_ascii_ticker_token(token):
        return False
    return (
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(token.lower())}(?![A-Za-z0-9])",
            text_lower,
        )
        is not None
    )


def _token_matches_user_text(token: str, text: str, text_lower: str) -> bool:
    tok = (token or "").strip()
    if len(tok) < 2:
        return False
    if _is_ascii_ticker_token(tok):
        return _ascii_token_in_text(tok, text_lower)
    return tok in text


def _has_memory_save_phrase(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in _MEMORY_SAVE_PATTERNS)


def user_requests_memory_save(user_input: str) -> bool:
    return _has_memory_save_phrase(user_input)


def user_requests_persona_change(user_input: str) -> bool:
    text = (user_input or "").strip()
    return any(re.search(p, text, re.IGNORECASE) for p in _PERSONA_PATTERNS)


def user_requests_forget(user_input: str) -> bool:
    text = (user_input or "").strip()
    return any(re.search(p, text, re.IGNORECASE) for p in _FORGET_PATTERNS)


def normalize_target_key(target: str) -> str:
    """重複判定用に target を正規化。"""
    t = (target or "").strip().lower()
    t = re.sub(r"[\s　_\-—–・/（）()【】\[\]「」『』]+", "", t)
    t = re.sub(r"[のはをがにとで]", "", t)
    return t


# 「GOOGL保有」と「GOOGL保有状況」は同一スロット。接頭辞が違う主体（妻の生年月日）は別。
_SAME_SLOT_SUFFIXES = ("状況", "情報", "のこと", "について")


def targets_are_same_slot(a: str, b: str) -> bool:
    """正規化キーが一致、または許可接尾辞だけの延長なら同一スロット。"""
    ka = normalize_target_key(a)
    kb = normalize_target_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    longer, shorter = (ka, kb) if len(ka) >= len(kb) else (kb, ka)
    if not longer.startswith(shorter):
        return False
    return longer[len(shorter):] in _SAME_SLOT_SUFFIXES


# 旧デモシード（偽プロフィール）。purge-junk で除去対象にする
_DEMO_SEED_QUOTES = {
    "コーヒーはブラック派かな",
    "辛いものはあんまり得意じゃない",
    "猫を2匹飼ってる",
    "ロックよりジャズが好き",
    "毎週金曜は早めに切り上げたい",
    "登山はきついから苦手",
    "在宅勤務がメイン",
    "映画は静かなドラマ系が好み",
    "甘いお酒は苦手、辛口が好き",
    "誕生日は特に祝わなくていい",
}


def is_demo_seed_memory(entry: dict) -> bool:
    quote = str(entry.get("quote") or "").strip()
    return quote in _DEMO_SEED_QUOTES


def is_junk_memory(entry: dict, user_input: str = "") -> bool:
    """ニュース・会話メタ・AI自己説明など長期記憶に不適切なエントリか。"""
    if is_demo_seed_memory(entry):
        return True
    summary = entry.get("summary") or {}
    target = str(summary.get("target") or "")
    note = str(summary.get("note") or "")
    quote = str(entry.get("quote") or "")
    category = str(entry.get("category") or "")
    stance = str(summary.get("stance") or "")
    tags = summary.get("tags") or []
    tag_set = {str(t).strip() for t in tags if t is not None}

    if category == "persona":
        return False

    # 圧縮由来の一時タグは常に junk（明示保有でもタグ付きは圧縮由来）
    if tag_set & _EPHEMERAL_KV_TAGS:
        return True

    # ユーザー本人の嗜好・保有・予定はニュース語を含んでも許容
    # ただし「GOOGL保有」のように明示保有のみ。単なる話題名の profile は落とす。
    # 「非保有者」などに含まれる「保有」は除外
    user_owned = bool(
        re.search(r"(?<!非)保有|持ってる|飼って|住んで|勤め|勤務", f"{note}{quote}{target}")
    )
    explicit_save_quote = _has_memory_save_phrase(quote) or _has_memory_save_phrase(user_input)
    if category in ("preference", "schedule") and stance in ("好き", "苦手", "条件付き", "予定", "約束"):
        return False
    if user_owned and category == "profile" and explicit_save_quote:
        if not re.search(r"(移籍金|画像リクエスト|APIエラー|キャラクター設定|移籍市場)", f"{target}{note}"):
            return False

    blob = f"{target}\n{note}\n{quote}"
    if _JUNK_TARGET_RE.search(blob):
        return True

    if _QUOTE_IS_META_RE.search(quote.strip()):
        return True

    # quote が短すぎ／ターゲット名だけのものは会話断片
    if len(quote.strip()) < 4 and category == "profile":
        return True

    # 「話題の固有名詞をそのまま記憶」パターン（明示保存の引用がない）
    if category == "profile" and not explicit_save_quote:
        qn = re.sub(r"[\s　]+", "", quote)
        tn = re.sub(r"[\s　]+", "", target)
        if qn and tn and (qn == tn or qn in tn or tn in qn):
            return True

    return False


def quote_supported_by_user(user_input: str, quote: str) -> bool:
    """quote が今回のユーザー発言に実際に含まれるか（捏造引用を防ぐ）。"""
    q = (quote or "").strip()
    u = (user_input or "").strip()
    if not q or not u:
        return False
    if q in u:
        return True
    # ゆるい一致: 句読点除去後に主要部分が含まれる
    q_norm = re.sub(r"[\s　、。！？!?,.]+", "", q)
    u_norm = re.sub(r"[\s　、。！？!?,.]+", "", u)
    if len(q_norm) >= 6 and q_norm in u_norm:
        return True
    # 長い quote は先頭20文字で判定
    if len(q_norm) >= 20 and q_norm[:20] in u_norm:
        return True
    return False


def should_accept_kv_action(user_input: str, kv_action: dict) -> tuple[bool, str]:
    """
    Supervisor の kv_action を受け入れるか。

    Returns:
        (ok, reason)
    """
    if not isinstance(kv_action, dict):
        return False, "kv_action が不正"

    action = kv_action.get("action") or "none"
    if action in (None, "none", ""):
        return False, "action=none"

    category = (kv_action.get("category") or "").strip()
    quote = kv_action.get("quote") or ""
    summary = kv_action.get("summary") or {}

    if action == "delete":
        if user_requests_forget(user_input) or user_allows_memory_use(user_input):
            return True, "forget/use"
        return False, "削除は明示的な忘却指示が必要"

    if action == "update":
        if user_requests_memory_save(user_input) or user_allows_memory_use(user_input):
            return True, "explicit save/use"
        return False, "更新は明示的な記憶指示が必要"

    if action != "add":
        return False, f"未知の action: {action}"

    # --- add ---
    if category == "persona":
        if user_requests_persona_change(user_input):
            return True, "persona change"
        return False, "persona は明示的な口調変更時のみ"

    if category == "exclusion":
        if user_requests_forget(user_input):
            return True, "exclusion"
        return False, "exclusion は忘却指示時のみ"

    # 明示保存が必須（「おまかせ」「はい」では保存しない）
    if not user_requests_memory_save(user_input):
        return False, "明示的な保存指示がない（おまかせ等は不可）"

    if is_junk_memory(kv_action, user_input=user_input):
        return False, "ジャンク（ニュース/会話メタ/AI自己説明）"

    if not quote_supported_by_user(user_input, quote):
        # 明示保存時でも quote はユーザー発言由来であること
        # 例外: quote が空で summary.note にユーザー文がある場合は note を見る
        note = str(summary.get("note") or "")
        if not quote_supported_by_user(user_input, note):
            return False, "quote がユーザー発言に存在しない"

    target = str(summary.get("target") or "")
    if not target.strip():
        return False, "target が空"

    return True, "explicit save"


_APPEND_RE = re.compile(
    r"追記|書き足|足して覚えて|に足して|\bappend\b",
    re.IGNORECASE,
)
_EDIT_EXISTING_RE = re.compile(
    r"の記憶に|のプロフィールに|に追記|を更新|を足して|"
    r"add to .{0,24}memory|update .{0,24}profile",
    re.IGNORECASE,
)


def user_requests_memory_append(user_input: str) -> bool:
    return bool(_APPEND_RE.search(user_input or ""))


def should_edit_existing_memory(user_input: str) -> bool:
    """既存行への追記・更新か（新規スロット追加ではない）。"""
    return user_requests_memory_append(user_input) or bool(_EDIT_EXISTING_RE.search(user_input or ""))


def merge_memory_note(old: str, new: str) -> str:
    old_s = (old or "").strip()
    new_s = (new or "").strip()
    if not new_s:
        return old_s
    if not old_s:
        return new_s
    if new_s in old_s:
        return old_s
    return f"{old_s.rstrip('。./')}。{new_s}"


def find_entry_for_memory_edit(user_input: str, memories: list[dict]) -> dict | None:
    """発話の人名/家族スロットに最も近い既存行。好みの汎用行（ヨーグルト）は選ばない。"""
    text = (user_input or "").strip()
    if not text or not memories:
        return None
    text_lower = text.lower()
    scored: list[tuple[int, int, dict]] = []
    for entry in memories:
        if entry.get("category") == "exclusion":
            continue
        blob = _entry_blob(entry)
        score = 0
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{1,15}", blob):
            if _ascii_token_in_text(m.group(0), text_lower):
                score += 5
        tag = entry_family_tag(entry)
        if tag == FAMILY_TAG_CHILD and _CHILD_MEMBER_RE.search(text):
            score += 3
        if tag == FAMILY_TAG_SPOUSE and _SPOUSE_RE.search(text):
            score += 3
        if score:
            scored.append((score, int(entry.get("id") or 0), entry))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


def build_append_update(existing: dict, kv_action: dict) -> dict:
    """既存の target / quote / 家族フラグは残し、note と tags だけ足す。"""
    incoming = kv_action.get("summary") or {}
    old = existing.get("summary") or {}
    tags = list(old.get("tags") or [])
    for tag in incoming.get("tags") or []:
        if tag and tag not in tags:
            tags.append(tag)
    incoming_note = str(incoming.get("note") or "").strip()
    if not incoming_note:
        incoming_note = str(kv_action.get("quote") or "").strip()
    return {
        "category": existing.get("category"),
        "quote": existing.get("quote"),
        "summary": {
            "target": old.get("target"),
            "stance": old.get("stance") or incoming.get("stance"),
            "note": merge_memory_note(str(old.get("note") or ""), incoming_note),
            "tags": tags,
        },
    }


def resolve_kv_mutation(
    user_input: str,
    kv_action: dict,
    memories: list[dict],
) -> tuple[str, dict, int | None] | None:
    """add/update を実際の書き込みに落とす。追記は target_id 無しでも人名で既存行へ。"""
    if not isinstance(kv_action, dict):
        return None
    action = kv_action.get("action") or "none"
    if action not in ("add", "update", "delete"):
        return None

    if action == "delete":
        tid = kv_action.get("target_id")
        return (action, kv_action, int(tid) if tid is not None else None)

    existing = None
    raw_id = kv_action.get("target_id")
    if raw_id is not None and str(raw_id).strip() != "":
        try:
            want = int(raw_id)
            existing = next((e for e in memories if e.get("id") == want), None)
        except (TypeError, ValueError):
            existing = None

    if existing is None and (action == "update" or should_edit_existing_memory(user_input)):
        existing = find_entry_for_memory_edit(user_input, memories)

    if existing is not None and (action == "update" or should_edit_existing_memory(user_input)):
        payload = (
            build_append_update(existing, kv_action)
            if should_edit_existing_memory(user_input)
            else kv_action
        )
        return ("update", payload, int(existing["id"]))

    if action == "update":
        return None
    return ("add", kv_action, None)


def collect_memory_guard_keywords(memories: list[dict], user_input: str) -> list[str]:
    """
    後処理で無断言及を落とすためのキーワード一覧。
    ユーザー入力に既に出てくる語は除外（正当な言及を消さない）。
    """
    keywords: list[str] = []
    user = user_input or ""
    for m in memories or []:
        summary = m.get("summary") or {}
        target = str(summary.get("target") or "").strip()
        if len(target) < 2:
            continue
        if target in user:
            continue
        # 長すぎる target はノイズ
        if len(target) > 40:
            # 括弧前だけ使う
            target = re.split(r"[（(—\-]", target, 1)[0].strip()
        if 2 <= len(target) <= 40 and target not in user:
            keywords.append(target)
        for tag in summary.get("tags") or []:
            tag_s = str(tag).strip()
            if 2 <= len(tag_s) <= 20 and tag_s not in user and tag_s not in keywords:
                # 汎用語は除外
                if tag_s in {"好き", "苦手", "予定", "旅行", "重要", "仕事", "音楽"}:
                    continue
                keywords.append(tag_s)
    return keywords


def entry_matches_user_input(entry: dict, user_input: str) -> bool:
    """今回の発話と意味的に接点がある記憶か（キーワード一致）。"""
    text = (user_input or "").strip()
    if not text:
        return False
    text_lower = text.lower()
    summary = entry.get("summary") or {}
    target = str(summary.get("target") or "")
    note = str(summary.get("note") or "")
    tags = summary.get("tags") or []

    # target 全体または意味のある部分トークン
    if target and len(target) >= 2 and target in text:
        return True
    for tok in re.split(r"[\s　/／・、,（）()]+", target):
        if _token_matches_user_text(tok, text, text_lower):
            return True
    # target 内の ASCII ティッカー断片（例: MSFT保有状況 → MSFT）。社名エイリアス表は持たない。
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]{1,9}", target):
        if _ascii_token_in_text(m.group(0), text_lower):
            return True

    for tag in tags:
        tag_s = str(tag).strip()
        if _token_matches_user_text(tag_s, text, text_lower):
            return True

    # note の固有っぽい単語（長め）。ASCII は境界照合。
    for tok in re.findall(r"[A-Za-z]{3,}|\d{2,}|[一-龥ぁ-んァ-ン]{3,}", note):
        if _token_matches_user_text(tok, text, text_lower):
            return True
    return False
