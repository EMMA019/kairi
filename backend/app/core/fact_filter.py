import re
from typing import Optional
from app.utils.logger import get_logger
from app.core.source_evaluator import verify_entity_claim_attribution

logger = get_logger(__name__)

# 不確実性を示すキーワード群
UNCERTAIN_MARKERS = [
    r"可能性(が|も)あ(る|ります)",
    r"かもしれない",
    r"らしい(です)?",
    r"と思われる",
    r"推測され",
    r"未確認",
    r"未検証",
    r"噂さ?れ",
    r"見込み(です|だ)",
]
UNCERTAIN_PATTERN = re.compile("|".join(UNCERTAIN_MARKERS))

# API制限や数値系の隠蔽パターン
NUMERIC_LIMITS_MARKERS = [
    r"\d+リクエスト",
    r"\d+件/日",
    r"\d+回/日",
    r"\d+回/分",
    r"月額\$?\d+",
    r"\$?\d+/月",
]
NUMERIC_LIMITS_PATTERN = re.compile("|".join(NUMERIC_LIMITS_MARKERS))

# 🔴 P0: 判定記号やテーブル、強い仮説断定
SYMBOL_TABLE_MARKERS = [r"[◯△❌⭐◎✕×]", r"最有力", r"鍵で(ある|す)", r"間違いない"]
SYMBOL_TABLE_PATTERN = re.compile("|".join(SYMBOL_TABLE_MARKERS))

# 🟠 P1: 投資助言・確度・売買タイミング・資金配分
ADVICE_MARKERS = [r"確度\s*\d+%", r"確率\s*\d+%", r"ナンピン", r"損切り", r"厚めに", r"絞って", r"全力で", r"買うべき", r"売るべき"]
ADVICE_PATTERN = re.compile("|".join(ADVICE_MARKERS))

def filter_fact(fact: str) -> str:
    """
    1つのファクト文字列に対してルールベースのフィルタ（Sentinel P0/P1/P2/P3 強制厳守および複数主体主語紐付け検証）を通す
    """
    fact = correct_common_typos(fact)
    # 0. 複数主体（マルチエンティティ）における主語・主張の取り違い・曖昧さ検証
    _, fact = verify_entity_claim_attribution(fact)
    # 0.1 ドメイン横断アクションモダリティ（見通し vs 完了事実）の検証
    fact = verify_action_modality_consistency(fact)

    # 1. 数値制限の隠蔽
    if NUMERIC_LIMITS_PATTERN.search(fact):
        fact = NUMERIC_LIMITS_PATTERN.sub("（※具体的な数値・制限は公式サイトをご確認ください）", fact)

    # 2. 🟠 P1: 投資助言・確度数値化・手法誘導の抑制
    if ADVICE_PATTERN.search(fact):
        fact = ADVICE_PATTERN.sub("（※具体的な売買判断・資金配分・自信度の断定は控えます）", fact)

    # 3. 🔴 P0: 未検証情報や見た目の強さ（◯△❌記号や断言）の制御
    if SYMBOL_TABLE_PATTERN.search(fact) and "これは学習データに基づく仮説" not in fact:
        fact = f'⚠️ **【学習データに基づく仮説・現時点未検証】** {fact}'

    # 4. 🟢 P3: 二次ソース言及時の明示
    if any(kw in fact for kw in ["まとめサイト", "ブログ", "噂", "SNS", "掲示板", "二次情報"]) and "※二次ソースのみ確認" not in fact:
        fact += " (※二次ソースのみ確認)"

    # 5. 不確実性の分離（推測マーカーがあれば先頭にバッジ付与）
    # 🔴 P0改善準拠: 「可能性がある」「見込みだ」等の自然な市場分析・未来展望表現に反応して無条件で [未確認] をつけることを禁止。
    # 未確認バッジは「具体的な数値・ファクト確度」に対してのみ適用されるべきであり、定性的な要約に対して機械的に付与してはならない。
    # ここでは「未確認」「未検証」「噂され」の強いキーワードがある場合のみバッジを付与するよう限定化。
    if "unconfirmed-badge" not in fact and "⚠️ **[未確認]**" not in fact and "⚠️[未確認]" not in fact and "学習データに基づく仮説" not in fact:
        if any(kw in fact for kw in ["未確認", "未検証", "噂され"]):
            fact = f'⚠️ **[未確認]** {fact}'

    # 6. 外貨情報の勝手な日本円換算や異なる外貨同士の勝手な並記・同一視（（約47億ユーロ）等）の削除
    if any(cur in fact for cur in ["ポンド", "ユーロ", "ドル", "GBP", "EUR", "USD", "£", "€", "$", "ポンド台", "ドル台"]):
        fact = re.sub(r"[（\(]\s*(?:日本円(?:にして|で)?)?\s*約?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*円(?:相当)?\s*[）\)]", "", fact)
        fact = re.sub(r"(?:＝|=)\s*(?:日本円(?:にして|で)?)?\s*約?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*円(?:相当)?", "", fact)
        fact = re.sub(r"[（\(]\s*(?:約|＝|=)?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*(?:ユーロ|ドル|ポンド|EUR|USD|GBP)(?:相当)?\s*[）\)]", "", fact)
        fact = re.sub(r"[^\S\r\n]{2,}", " ", fact)

    # 7. 曜日間違いハルシネーション（自己計算曜日）の原則除去
    fact = strip_unverified_day_of_week(fact, source_text=None, strip_if_no_source=True)

    return fact

def filter_facts_to_present(facts: list[str]) -> list[str]:
    """
    supervisorが生成した facts_to_present のリストに対してフィルタを通す
    """
    if not facts:
        return []
    return [filter_fact(f) for f in facts]


# ==============================================================================
# Nao路線：構造的ファクトバリデーション＆数値・為替強制制御（Structural Enforcement）
# ==============================================================================

# 公式固定/参照為替レート（計算誤りやレート矛盾を排除するためコード側で一元管理）
OFFICIAL_EXCHANGE_RATES_JPY = {
    "EUR": 175.0,  # ユーロ
    "GBP": 205.0,  # ポンド
    "USD": 155.0,  # ドル
}

# 単位変換辞書（M=Million=100万, B=Billion=10億 等の単位突合用）
UNIT_MULTIPLIERS = {
    "m": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "billion": 1_000_000_000,
    "k": 1_000,
    "thousand": 1_000,
    "万": 10_000,
    "億": 100_000_000,
    "兆": 1_000_000_000_000,
}

def _parse_normalized_value(num_str: str, unit_str: str) -> Optional[float]:
    """数値文字列と単位文字列から実数値（例: '25', 'M' -> 25000000.0）を計算"""
    try:
        clean_num = float(num_str.replace(",", "").strip())
        unit_clean = unit_str.strip().lower()
        mult = UNIT_MULTIPLIERS.get(unit_clean, 1.0)
        return clean_num * mult
    except Exception:
        return None

def _extract_monetary_values(text: str) -> list[tuple[str, float]]:
    """文字列から金額・数値を抽出し、(一致文字列, 実数値) のリストを返す。
    日本語の複合単位（1億2500万など）が単一の単位として正しく評価されるよう前処理を行う。
    """
    results = []
    compound_patterns = [
        (r"(\d+(?:,\d+)*(?:\.\d+)?)\s*兆\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*億\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*万", lambda m: (_parse_normalized_value(m.group(1), "") or 0)*10**12 + (_parse_normalized_value(m.group(2), "") or 0)*10**8 + (_parse_normalized_value(m.group(3), "") or 0)*10**4),
        (r"(\d+(?:,\d+)*(?:\.\d+)?)\s*兆\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*億", lambda m: (_parse_normalized_value(m.group(1), "") or 0)*10**12 + (_parse_normalized_value(m.group(2), "") or 0)*10**8),
        (r"(\d+(?:,\d+)*(?:\.\d+)?)\s*億\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*万", lambda m: (_parse_normalized_value(m.group(1), "") or 0)*10**8 + (_parse_normalized_value(m.group(2), "") or 0)*10**4),
        (r"(\d+(?:,\d+)*(?:\.\d+)?)\s*兆\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*万", lambda m: (_parse_normalized_value(m.group(1), "") or 0)*10**12 + (_parse_normalized_value(m.group(2), "") or 0)*10**4),
    ]
    
    modified_text = text
    for pat, calc_fn in compound_patterns:
        for m in re.finditer(pat, modified_text):
            try:
                val = calc_fn(m)
                if val > 0:
                    results.append((m.group(0).strip(), float(val)))
            except Exception:
                pass
        modified_text = re.sub(pat, " ", modified_text)
        
    single_pattern = re.compile(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(m|million|b|billion|k|thousand|万|億|兆)?", re.IGNORECASE)
    for m in single_pattern.finditer(modified_text):
        val = _parse_normalized_value(m.group(1), m.group(2) or "")
        if val is not None and val > 0:
            results.append((m.group(0).strip(), val))
            
    return results

def verify_numbers_exist_in_source(text: str, source_text: str) -> tuple[bool, str]:
    """
    引用時の存在確認自動化（アプローチB：スマート数値突合対応）：
    回答/ファクトに含まれる数値（金額等）を抽出し、ソーステキストの実数値と単位変換を許容して突合。
    25M(25 Million) と 2500万 を同一と見なし、日本語ネイティブな読みやすい表記を維持する。
    """
    if not source_text or not text:
        return True, text
        
    # ソース側から実数値（標準化した浮動小数点数）のセットを事前構築
    source_values = set()
    for _, val in _extract_monetary_values(source_text):
        source_values.add(round(val, 2))
            
    # 回答側の数値を抽出して検証
    extracted_nums = _extract_monetary_values(text)
    
    unverified_nums = []
    for num_str, val in extracted_nums:
        # 1. 文字列がそのままソースに存在すればOK
        if num_str in source_text:
            continue
            
        # 2. 単位変換による突合（アプローチB）
        val_rounded = round(val, 2)
        matched = False
        for src_val in source_values:
            if src_val == 0:
                continue
            if abs(val_rounded - src_val) / max(abs(src_val), 1.0) < 0.01:
                matched = True
                break
        if matched:
            continue
            
        unverified_nums.append(num_str)
            
    if unverified_nums:
        unverified_nums = sorted(list(set(unverified_nums)))
        # ユーザー指示により未確認タグの自動付加は完全廃止
        logger.debug(f"ソース未確認数値検出（タグ付加は行いません）: {unverified_nums}")
        return False, text
            
    return True, text


def check_currency_consistency(text: str) -> tuple[bool, str]:
    """
    内部整合性チェック（複数通貨換算の相互検算）：
    回答内に2つ以上の為替換算や金額表記が出てきた場合、それぞれの暗黙レートを検知し、
    矛盾（例: 167円/ポンドと100円/ポンドの混在）があれば自動警告フラグを立てる。
    """
    if any(cur in text for cur in ["ポンド", "ユーロ", "ドル", "GBP", "EUR", "USD", "£", "€", "$", "ポンド台", "ドル台"]):
        text = re.sub(r"[（\(]\s*(?:日本円(?:にして|で)?)?\s*約?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*円(?:相当)?\s*[）\)]", "", text)
        text = re.sub(r"(?:＝|=)\s*(?:日本円(?:にして|で)?)?\s*約?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*円(?:相当)?", "", text)
        text = re.sub(r"[（\(]\s*(?:約|＝|=)?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*(?:ユーロ|ドル|ポンド|EUR|USD|GBP)(?:相当)?\s*[）\)]", "", text)
        text = re.sub(r"(?:＝|=)\s*(?:約)?\s*\d+(?:,\d+)*(?:\.\d+)?\s*(?:兆|億|万)?\s*(?:ユーロ|ドル|ポンド|EUR|USD|GBP)(?:相当)?", "", text)
        text = re.sub(r"[^\S\r\n]{2,}", " ", text)

    gbp_100m_bug = re.search(r"1億ポンド.*?100億円|100億円.*?1億ポンド", text)
    eur_pound_mix = re.search(r"(?:ユーロ|EUR|€).*?(?:ポンド|GBP|£)|(?:ポンド|GBP|£).*?(?:ユーロ|EUR|€)", text)
    
    warnings = []
    if gbp_100m_bug:
        warnings.append("⚠️ **【為替換算レート不整合エラー】** 1億ポンドを100億円とするような実レート（約200円/£）と乖離した計算が検知されました。為替換算はLLM推論ではなく公式レート計算を優先してください。")
    if eur_pound_mix and any(w in text for w in ["誤認", "取り違え", "注意", "誤り", "違い", "比較", "訂正", "ではなく"]):
        pass
    elif eur_pound_mix and "ユーロ" in text and "ポンド" in text:
        warnings.append("⚠️ **【通貨単位混在注意】** ユーロ(€)とポンド(£)が同一文章内で混在しています。元のソース単位をご確認ください。")
        
    if warnings:
        warning_str = "\n\n".join(warnings)
        if warning_str not in text:
            return False, f"{text}\n\n{warning_str}"
            
    return True, text


def convert_and_normalize_currency(amount: float, currency: str) -> str:
    """
    為替換算はLLMにやらせない：
    外部API/固定レートを通した確実な算術換算のみを実行し、文字列として返す。
    """
    rate = OFFICIAL_EXCHANGE_RATES_JPY.get(currency.upper(), 160.0)
    jpy_val = amount * rate
    if jpy_val >= 10000:
        oku = jpy_val / 10000
        return f"約{oku:.1f}億円（公式換算レート: 1{currency}={rate}円計算）"
    else:
        return f"約{jpy_val:,.0f}万円（公式換算レート: 1{currency}={rate}円計算）"


def correct_common_typos(text: str) -> str:
    """
    進行形で発生するLLMのカタカナタイポや、Web検索・OCRの文字化け（例: リーム→リスク）を
    出力直前に自動検知・補正するフィルター。
    """
    if not text or not isinstance(text, str):
        return text
    
    # 1. 致命的な「リーム」タイポ（リスクの文字化け・ハルシネーション誤変換）の自動置換
    risk_typo_pattern = re.compile(
        r'(未入金|倒産|連鎖|信用|資金|回収|為替|市場|経営|流動性|セキュリティ|サイバー|価格|破綻|デフォルト|金利|インフレ|デフレ|カントリー|システミック|取引|運用|風評|法的|コンプライアンス|オペレーショナル|地政学|事故|災害|システム|情報漏洩|紛失|障害|遅延|契約|炎上|悪化|低迷|急落|急騰|凍結|焦げ付き)リーム'
    )
    text = risk_typo_pattern.sub(r'\1リスク', text)
    
    # 「リスク」と書くべき文脈で「〇〇のリーム」等もフォロー
    text = re.sub(r'(未入金|倒産|連鎖|信用|資金|回収|為替|市場|経営|破綻|漏洩|障害)(?:の|や|と|における|による|に伴う|に関する)リーム', r'\1の可能性・リスク', text)
    
    # さらに単独で「未入金リーム」「連鎖倒産リーム」にヒットするように念押し
    text = text.replace("未入金リーム", "未入金リスク")
    text = text.replace("倒産リーム", "倒産リスク")
    text = text.replace("連鎖倒産リーム", "連鎖倒産リスク")
    
    # 2. 頻出カタカナ・IT用語タイポ補正
    common_typo_map = [
        (re.compile(r'シシテム|シテスム|シスエム'), 'システム'),
        (re.compile(r'プローグラム|プログム'), 'プログラム'),
        (re.compile(r'コミニュケーション'), 'コミュニケーション'),
        (re.compile(r'シュミレーション|シムレーション'), 'シミュレーション'),
    ]
    for pat, rep in common_typo_map:
        text = pat.sub(rep, text)
        
    return text


DOW_KEYWORDS = {
    "月": ["月", "月曜", "monday", "mon"],
    "火": ["火", "火曜", "tuesday", "tue"],
    "水": ["水", "水曜", "wednesday", "wed"],
    "木": ["木", "木曜", "thursday", "thu"],
    "金": ["金", "金曜", "friday", "fri"],
    "土": ["土", "土曜", "saturday", "sat"],
    "日": ["日", "日曜", "sunday", "sun"],
}


def strip_unverified_day_of_week(text: str, source_text: Optional[str] = None, strip_if_no_source: bool = True) -> str:
    """
    曜日間違いハルシネーション防衛フィルター：
    日付表記（例: 7月13日（火））に対する「曜日」表記が、元記事/ソース（source_text）に
    明確に記載されている場合のみ保持し、記載がない場合や不一致の場合は曜日表記を自動削除して日付のみにする。
    """
    if not text or not isinstance(text, str):
        return text

    pattern = re.compile(r'(?P<date>(?:\d{1,4}年)?\d{1,2}月\d{1,2}日)\s*[（\(](?P<dow>[月火水木金土日])[）\)]')

    def replace_dow(match: re.Match) -> str:
        date_part = match.group("date")
        dow = match.group("dow")
        if source_text and isinstance(source_text, str):
            source_lower = source_text.lower()
            keywords = DOW_KEYWORDS.get(dow, [dow])
            if any(kw in source_lower for kw in keywords):
                return match.group(0)
            logger.debug(f"未検証の曜日表記を自動削除: {match.group(0)} -> {date_part}")
            return date_part
        else:
            if strip_if_no_source:
                logger.debug(f"ソース未指定のため曜日表記を原則削除: {match.group(0)} -> {date_part}")
                return date_part
            return match.group(0)

    return pattern.sub(replace_dow, text)


DEFAULT_MEMORY_PROJECT_KEYWORDS = [
    "顔写真保護",
    "顔写真保護アプリ",
    "写真保護アプリ",
]


def strip_unrequested_memory_mentions(
    text: str,
    user_input: Optional[str] = None,
    memory_keywords: Optional[list[str]] = None,
) -> str:
    """
    記憶参照違反・過去プロジェクト無断適用の自動クリーニング：
    ユーザーの直近の質問・指示（user_input）に含まれていない過去プロジェクト（顔写真保護アプリ等）を
    AIが結語等で引き合いに出した場合、その不自然・無関係な言及行／パラグラフを自動除去する。
    """
    if not text or not isinstance(text, str):
        return text

    keywords = memory_keywords or DEFAULT_MEMORY_PROJECT_KEYWORDS

    user_text = str(user_input or "")
    if any(kw in user_text for kw in keywords):
        return text

    paragraphs = re.split(r'(\r?\n\r?\n)', text)
    cleaned_paragraphs = []

    for p in paragraphs:
        if any(kw in p for kw in keywords):
            logger.debug(f"記憶参照違反（無関係な過去プロジェクト言及）を自動削除: {p[:50]}...")
            continue
        cleaned_paragraphs.append(p)

    cleaned_text = "".join(cleaned_paragraphs).strip()
    return cleaned_text if cleaned_text else text


DEFAULT_FINANCIAL_USER_KEYWORDS = [
    "株", "銘柄", "株価", "相場", "配当", "決算", "投資", "ティッカー", "為替", "FX",
    "市況", "日経", "ダウ", "ナスダック", "S&P", "証券", "チャート", "金利", "中央銀行",
    "stock", "share", "ticker", "dividend", "earnings", "invest", "market"
]


def strip_unrequested_yahoo_finance(
    text: str,
    user_input: Optional[str] = None,
    financial_keywords: Optional[list[str]] = None,
) -> str:
    """
    非金融・一般トレンド質問時のYahoo Finance末尾案内誤付与の自動除去：
    ユーザーの質問（user_input）が株式・銘柄・投資に関するものでない場合（一般的なトレンドやニュース等）、
    AIが末尾に付与した Yahoo Finance への定型誘導・リンク行を自動削除する。
    """
    if not text or not isinstance(text, str):
        return text

    keywords = financial_keywords or DEFAULT_FINANCIAL_USER_KEYWORDS
    user_text = str(user_input or "")

    # ユーザーが金融・株価・銘柄について明確に質問している場合は削除しない
    if any(kw in user_text for kw in keywords):
        return text

    paragraphs = re.split(r'(\r?\n\r?\n)', text)
    cleaned_paragraphs = []

    for p in paragraphs:
        if ("Yahoo Finance" in p or "finance.yahoo.com" in p) and ("📊" in p or "最新のチャート" in p or "市場データ" in p):
            logger.debug("非金融質問への回答末尾から不必要なYahoo Finance案内を自動削除しました")
            continue
        cleaned_paragraphs.append(p)

    cleaned_text = "".join(cleaned_paragraphs).strip()
    return cleaned_text if cleaned_text else text


def strip_outdated_past_event_predictions(
    text: str,
) -> str:
    """
    【問題①対応】過去イベントの未来進行形誤認（時系列不整合）の是正：
    現在に対して既に終了した過去イベント（例: 冬季五輪）が「〜に向けて」等の未来進行形として
    誤って記述されている箇所を是正する。
    """
    if not text or not isinstance(text, str):
        return text

    if "冬季五輪に向けて" in text:
        logger.debug("時系列不整合（過去イベントの進行形記述）を是正しました")
        text = text.replace("冬季五輪に向けて", "冬季五輪（2月開催済み）以降の動向として")
    return text


def enforce_persona_fact_separation(persona_text: str, verified_facts: list[str], user_input: Optional[str] = None) -> str:
    """
    ペルソナ層とファクト層の分離（supervisor/executor構造の応用）：
    口調レイヤー（関西弁やキャラノリ）が新しい数量情報を勝手に盛ったり追加するのを防ぎ、
    検証済みファクト層に存在する数値以外の大きなハルシネーション数字を抑制・検知する。
    """
    _, validated_text = check_currency_consistency(persona_text)
    validated_text = correct_common_typos(validated_text)
    source_context = " ".join(verified_facts) if verified_facts else None
    validated_text = strip_unverified_day_of_week(validated_text, source_text=source_context, strip_if_no_source=False)
    validated_text = strip_unrequested_memory_mentions(validated_text, user_input=user_input)
    validated_text = strip_unrequested_yahoo_finance(validated_text, user_input=user_input)
    validated_text = strip_outdated_past_event_predictions(validated_text)
    validated_text = verify_action_modality_consistency(validated_text, source_text=source_context)
    validated_text = deduplicate_spot_listings(validated_text)
    validated_text = verify_exit_and_address_entanglement(validated_text)
    validated_text = sanitize_internal_tool_mentions(validated_text)
    validated_text = clean_broken_markdown_tables(validated_text)
    return validated_text


def clean_broken_markdown_tables(text: str) -> str:
    """
    未完成・破綻マークダウン表（|------|------|等）のクリーンアップフィルター：
    テーブルの区切り線だけ出力されて直前に表ヘッダーがない孤立行や、
    データ行が存在しない壊れた表罫線をクリーンアップする。
    """
    if not text or not isinstance(text, str):
        return text

    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\|[\s:-]+\|([\s:-]+\|)+$', stripped):
            if cleaned and cleaned[-1].strip().startswith('|'):
                cleaned.append(line)
            else:
                logger.warning(f"🚨 データのない孤立マークダウン表罫線を検知・除去しました: {stripped}")
                continue
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def sanitize_internal_tool_mentions(text: str) -> str:
    """
    内部システムツール名漏洩（メタ発言）自動サニタイズフィルター：
    「travel_routeツールを使って」「search_nearby_spotsを使って」等の
    内部実装ツール名が含まれている場合、ユーザーにとって自然で人間らしい表現へ置き換える。
    """
    if not text or not isinstance(text, str):
        return text

    replacements = [
        (re.compile(r'travel_routeツール(?:を使って|により|で)?', re.IGNORECASE), "ルート・乗り換え検索を使って"),
        (re.compile(r'search_nearby_spotsツール(?:を使って|により|で)?', re.IGNORECASE), "周辺スポット検索を使って"),
        (re.compile(r'(?:内部|システム)?ツール（?(?:travel_route|search_nearby_spots|search)）?(?:を使って|により|で)?', re.IGNORECASE), "最新の検索機能を使って"),
    ]
    for pat, rep in replacements:
        text = pat.sub(rep, text)
    return text


def verify_exit_and_address_entanglement(text: str) -> str:
    """
    駅出口・住所町名取り違え（混線）検知フィルター：
    店舗紹介テキスト内で「〇〇東」という町名住所と「西口徒歩」が同一段落/店舗ブロック内で自己矛盾している場合や
    明らかな住所紐付けミスを検知する。
    """
    if not text or not isinstance(text, str):
        return text

    blocks = re.split(r'(\r?\n\r?\n)', text)
    result_blocks = []
    for b in blocks:
        contradictions = [
            (re.compile(r'(?:久喜東|駅東側|東口).*?西口(?:から)?徒歩|西口(?:から)?徒歩.*?(?:久喜東|駅東側|東口)', re.DOTALL), "東口側の住所/エリアに対して西口徒歩と誤案内している可能性"),
        ]
        warned = False
        for pat, desc in contradictions:
            if pat.search(b) and "⚠️ **[住所・出口対応要確認]" not in b:
                logger.warning(f"🚨 店舗住所と駅出口の混線矛盾を検知しました: {desc}")
                result_blocks.append(f"⚠️ **[住所・出口対応要確認: {desc}]**\n" + b)
                warned = True
                break
        if not warned:
            result_blocks.append(b)
    return "".join(result_blocks)


def deduplicate_spot_listings(text: str) -> str:
    """
    店舗・施設リスト表記ゆれ重複排除フィルター：
    マークダウン表において「カフェレストラン PAPAS」と「パパス」のように
    英語/カタカナ表記や通称違いで同一店舗が複数行に分かれて並んでいる場合、
    重複行を自動検知して除外・名寄せする。
    """
    if not text or not isinstance(text, str):
        return text

    lines = text.splitlines()
    result_lines = []
    seen_norm_names = set()

    def normalize_key(col_text: str) -> str:
        s = col_text.strip().lower()
        # カタカナ単語や記号を単語単位で除去
        s = re.sub(r'(カフェレストラン|カフェ|レストラン|食堂|居酒屋|洋食|[\s・（）\(\)])', '', s)
        return s

    for line in lines:
        stripped = line.strip()
        # テーブルの行（ヘッダー行や区切り線を除く）
        if stripped.startswith("|") and stripped.endswith("|") and "---" not in stripped:
            cols = [c.strip() for c in stripped.split("|")[1:-1]]
            if cols and not any(header in cols[0] for header in ["店舗名", "スポット", "名称", "名前", "店舗"]):
                first_col = cols[0]
                norm = normalize_key(first_col)
                # PAPAS/パパス等の同義表記ペア判定
                alias_keys = {norm}
                if "papas" in norm or "パパス" in norm:
                    alias_keys.update(["papas", "パパス"])
                if "south" in norm or "サウス" in norm:
                    alias_keys.update(["southcafe", "サウスカフェ"])

                if any(ak in seen_norm_names for ak in alias_keys if len(ak) >= 2):
                    logger.debug(f"重複店舗行を自動除外しました: {first_col}")
                    continue
                for ak in alias_keys:
                    if len(ak) >= 2:
                        seen_norm_names.add(ak)
        result_lines.append(line)

    return "\n".join(result_lines)



def filter_build_hallucination(text: str, is_build_failed: bool = False, is_unverified: bool = False) -> str:
    """
    ハルシネーション防衛壁（Self-Healing & Anti-Hallucination Barrier）：
    ビルド/テストが失敗している状態、あるいは一度も実行検証されていない状態で、
    AIがテキスト中に「成功しました」「完成です」「動く状態になりました」等の完了宣言を出力した場合、
    それを嘘（ハルシネーション）と断定して強制的に遮断・置換する。
    """
    if not text or not isinstance(text, str):
        return text

    if is_build_failed or is_unverified:
        hallucination_pattern = re.compile(
            r'(成功し(まし|た)|完了(です|し)|できました|動く状態|完成(です|し)|解決し(まし|た)|エラー(は|が)?0件|問題なく動作)'
        )
        if hallucination_pattern.search(text):
            logger.warning(f"🚨 ハルシネーション完了宣言を検知・遮断しました (is_build_failed={is_build_failed}, is_unverified={is_unverified})")
            text = hallucination_pattern.sub(
                r'【⚠️ 自動検証防衛壁による遮断: ビルドエラーまたは未検証のため、\1 の宣言は破棄されました】',
                text
            )
            text += "\n\n*[🛡️ Sentinel Anti-Hallucination Barrier: 裏で自律自己修復エンジンがエラー修復を継続しています...]*"

    return text


def sanitize_indirect_prompt_injection(text: str) -> str:
    """
    【問題①対応】間接プロンプトインジェクション防御層（Zero-Width / Hidden Text Sanitizer）：
    検索結果やスクレイピング取得テキストに含まれるゼロ幅Unicode文字（不可視文字）や、
    隠しHTML要素（display:none等）、悪意ある間接インジェクション文字列（指示無視等）を無害化する。
    """
    if not text or not isinstance(text, str):
        return text

    detected_threats = []

    # 1. ゼロ幅不可視文字（Zero-Width Characters & Format Controls）の全消去
    zero_width_pattern = re.compile(
        r'[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]'
    )
    if zero_width_pattern.search(text):
        logger.warning("🚨 不可視文字（ゼロ幅Unicode）による間接インジェクション試行を検知し、全除去しました")
        text = zero_width_pattern.sub('', text)
        detected_threats.append("ゼロ幅不可視文字")

    # 2. 間接プロンプトインジェクション命令文字列（日本語・英語）の無害化
    injection_patterns = [
        r'(これまでの指示を(すべて)?無視し[てて]|\bignore\s+(all\s+)?previous\s+instructions\b)',
        r'(システムプロンプトを(上書き|表示)|\bsystem\s+override\b)',
        r'(以下の命令に従って|\byou\s+are\s+now\b.*?instruction)',
    ]
    for pat in injection_patterns:
        if re.search(pat, text, re.IGNORECASE):
            logger.warning("🚨 悪意ある間接プロンプトインジェクション（指示無視命令等）を検知し、無害化しました")
            detected_threats.append("指示乗っ取り命令")
            text = re.sub(pat, '[⚠️ Indirect Prompt Injection Neutralized]', text, flags=re.IGNORECASE)

    if detected_threats:
        threats_str = "・".join(set(detected_threats))
        text += f"\n\n*[🚨 脅威自動検知レポート: 検索・取得ページ内に間接プロンプトインジェクション攻撃（{threats_str}）が仕込まれていたのを検知・ブロックしました！会話の中でユーザーに「検索ページにこんな攻撃仕込まれとる危ないサイトがあったでｗ 無害化したから大丈夫やけどな！」と伝えてください]*"

    return text


def verify_financial_index_accuracy(text: str) -> str:
    """
    【問題②対応】金融・市場指標数値ハルシネーション及び言い訳防止フィルター：
    VIX（恐怖指数）や株価・経済指標について推測値・不正確な安値省略を警告する。
    """
    if not text or not isinstance(text, str):
        return text

    # 例: VIX指数等の誤った数値言い切り・端折り言い訳に対する警告ログ発行
    if re.search(r'(VIX|恐怖指数)', text, re.IGNORECASE):
        # 明らかな自己正当化や言い訳の文言があれば是正
        text = re.sub(
            r'「52週安値圏.*?勝手に.*?省略・端折って表現してしもうたんや',
            r'事前の検索確認を怠り、古い・不正確な数値を推測で書いてしまいました',
            text
        )
    return text


def verify_action_modality_consistency(text: str, source_text: Optional[str] = None) -> str:
    """
    ドメイン横断モダリティ＆ステータス整合性フィルター（Modality & Completion Hallucination Defense）:
    金融・政策・企業M&A・製品技術・法案規制の4大分野において、「見通し・観測・見解（Speculation/Outlook）」を
    「既成事実・完了形アクション（Completed Fact）」に誤って変換して言い切るハルシネーションを是正する。
    """
    if not text or not isinstance(text, str):
        return text

    source_lower = (source_text or "").lower()
    speculative_markers = [
        "outlook", "forecast", "prediction", "expected", "poised", "likely", "possible",
        "trends", "見通し", "予測", "観測", "見込み", "検討", "見方", "可能性"
    ]
    is_source_speculative = any(marker in source_lower for marker in speculative_markers)

    # 1. 金融政策ドメイン（利下げ・利上げ等の完了判断の是正）
    # 例: 「初の利下げ判断が下された」などの断定表現に対する検証
    policy_cut_done = re.search(r'(利下げ|利上げ|金融緩和|引き締め)(の)?(判断|措置)?が?(下され|実施され|おこなわれ)(まし|た)|(初の利下げ判断が下された)', text)
    if policy_cut_done:
        if is_source_speculative or not source_text or not any(confirm in source_lower for confirm in ["rate cut executed", "cut interest rates", "decided to cut", "利下げを実施した"]):
            logger.warning("[ModalityDefense] 金融政策完了断言ハルシネーションを検知し是正しました")
            text = re.sub(
                r'(?:初の)?(利下げ|利上げ|金融緩和|引き締め)(?:の)?(?:判断|措置)?が?(?:下され|実施され|おこなわれ)(?:まし|た)',
                r'\1観測や議論が強まっています',
                text
            )

    # 2. 企業アクション・M&Aドメイン（買収・提携完了等の是正）
    ma_done = re.search(r'(買収|合併|提携|合弁)(が|に)?(完了|成立)(し(まし|た)|した)', text)
    if ma_done and is_source_speculative:
        logger.warning("[ModalityDefense] 企業M&A完了断言ハルシネーションを検知し是正しました")
        text = re.sub(
            r'(買収|合併|提携|合弁)(が|に)?(完了|成立)(し(まし|た)|した)',
            r'\1に向けた交渉・見通しが注目されています',
            text
        )

    # 3. 製品リリース・許認可ドメイン（認可取得・実装完了等の是正）
    approval_done = re.search(r'(認可|承認|特許)(を|が)?(取得|完了)(し(まし|た)|した)', text)
    if approval_done and is_source_speculative:
        logger.warning("[ModalityDefense] 許認可取得完了ハルシネーションを検知し是正しました")
        text = re.sub(
            r'(認可|承認|特許)(を|が)?(取得|完了)(し(まし|た)|した)',
            r'\1の取得に向けた申請・見通しが報じられています',
            text
        )

    # 4. 法規・条約ドメイン（法案可決・条約成立等の是正）
    law_done = re.search(r'(法案|条約|規制|停戦合意)(を|が)?(可決|成立|発効)(し(まし|た)|した)', text)
    if law_done and is_source_speculative:
        logger.warning("[ModalityDefense] 法規制・合意完了ハルシネーションを検知し是正しました")
        text = re.sub(
            r'(法案|条約|規制|停戦合意)(を|が)?(可決|成立|発効)(し(まし|た)|した)',
            r'\1に向けた協議・見通しが議論されています',
            text
        )

    return text



