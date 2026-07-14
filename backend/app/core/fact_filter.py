import re
from datetime import date, timedelta
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
    # 0.2 時代錯誤役職ハルシネーションの汎用検証
    fact = verify_temporal_leadership_claims(fact)
    # 0.3 時系列不一致の後付け合理化・縫い合わせ検証
    fact = verify_chronological_rationalization(fact)
    # 0.4 未確認店舗・名称未詳エンティティのリスト混入排除
    fact = filter_unknown_entity_listings(fact)
    # 0.5 バッファ汚染・残骸テキストの除去
    fact = sanitize_buffer_contamination(fact)

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
    validated_text = strip_out_of_period_event_mentions(validated_text)
    validated_text = verify_maintenance_date_relevance(validated_text, source_text=source_context, user_input=user_input)
    validated_text = verify_holiday_and_weekend_claims(validated_text)
    validated_text = strip_excuse_hallucinations(validated_text)
    return validated_text


def verify_holiday_and_weekend_claims(text: str) -> str:
    """
    祝日・連休関係の誤断定フィルター（動的祝日判定版）：
    jpholidayを使い、任意の日付に対して「〇連休の何日目か」を動的に正しく判定する。
    翌日（月曜）が祝日（海の日等）である場合の「日曜が3連休の最終日」といった誤認表現を補正する。
    """
    if not text or not isinstance(text, str):
        return text

    try:
        import jpholiday
    except ImportError:
        logger.warning("jpholidayが未インストールのため祝日連休チェックをスキップします")
        return text

    def _get_consecutive_holiday_position(d: date) -> tuple[int, int, str]:
        """指定日が連休の何日目か（1-indexed）と連休全体の日数、祝日名を返す"""
        # 連休の開始日を探す（前日も休みかどうか遡る）
        start = d
        while True:
            prev = start - timedelta(days=1)
            if prev.weekday() >= 5 or jpholiday.is_holiday(prev):  # 土日 or 祝日
                start = prev
            else:
                break
        # 連休の終了日を探す（翌日も休みかどうか進む）
        end = d
        while True:
            nxt = end + timedelta(days=1)
            if nxt.weekday() >= 5 or jpholiday.is_holiday(nxt):  # 土日 or 祝日
                end = nxt
            else:
                break
        total = (end - start).days + 1
        position = (d - start).days + 1
        holiday_name = jpholiday.is_holiday_name(d) or ""
        return position, total, holiday_name

    # 「〇月〇日が3連休の最終日」等の表現を検出
    date_pattern = re.compile(r'(\d{1,2})月(\d{1,2})日.*?(?:3|三|4|四|5|五)連休の(最終日|最後の日)')
    for m in date_pattern.finditer(text):
        try:
            month, day = int(m.group(1)), int(m.group(2))
            from datetime import datetime
            now = datetime.now()
            target = date(now.year, month, day)
            pos, total, hol_name = _get_consecutive_holiday_position(target)
            if total >= 3 and pos < total:
                # 最終日ではない → 補正
                if pos == 1:
                    pos_label = "初日"
                else:
                    pos_label = f"{pos}日目（中日）"
                old_text = m.group(0)
                new_text = re.sub(r'(?:最終日|最後の日)', pos_label, old_text)
                text = text.replace(old_text, new_text)
                logger.info(f"🗓️ 連休位置を動的補正しました: {old_text} → {new_text}")
        except (ValueError, OverflowError):
            pass

    # 汎用パターン: 「3連休の最終日曜日」等
    text = re.sub(r'(?:3|三)連休の最終日曜日', '3連休の中日（日曜日）', text)

    return text


def strip_excuse_hallucinations(text: str) -> str:
    """
    自己正当化・言い訳ハルシネーション除去フィルター（動詞ベース包括版）：
    「〇〇と混同した」「〇〇と勘違いした」「〇〇の日程を取り違えた」等の
    事実無根な弁明文章を動詞パターンで包括的に検知・除去する。
    """
    if not text or not isinstance(text, str):
        return text

    lines = text.splitlines()
    cleaned = []
    excuse_patterns = [
        # 動詞ベース包括パターン（「〜と混同」「〜と勘違い」「〜を取り違え」等）
        re.compile(r'.*(?:と混同(?:し(?:てしまい|まし)|した)|と勘違い(?:し(?:てしまい|まし)|した)|を取り違え(?:てしまい|まし|た)|を誤って適用|の日程と間違え).*', re.IGNORECASE),
        # セクション見出しパターン（「誤りの原因について」等）
        re.compile(r'^[\s*#-]*(?:誤りの原因|間違いの原因|混同の原因|誤認の理由)(?:について)?.*', re.IGNORECASE),
        # 弁明構文パターン（「これは〇〇を〇〇したものです」）
        re.compile(r'.*これは.*(?:混同|勘違い|取り違え|誤認).*(?:したもの|によるもの).*', re.IGNORECASE),
    ]
    for line in lines:
        stripped = line.strip()
        if any(pat.match(stripped) for pat in excuse_patterns):
            logger.info(f"🧹 言い訳ハルシネーション行を除去しました: {stripped}")
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def strip_out_of_period_event_mentions(text: str) -> str:
    """
    期間外イベントおよび終了済み催事の余計な言及行を除去するフィルター：
    「※〇〇は終了しております」「〇〇祭りは〇日まででした」等の
    ユーザーの訪問対象外期間に関する余計な注意書き・お節介行をクリーンアップする。
    """
    if not text or not isinstance(text, str):
        return text

    lines = text.splitlines()
    cleaned = []
    out_of_period_patterns = [
        re.compile(r'.*(?:あじさい祭|花火大会|祭り|催事|イベント|マラソン|フェス(?:ティバル)?|フリマ|フリーマーケット|コンサート|花見|紅葉|盆踊り|夏祭り|冬祭り|春祭り|秋祭り|クリスマスマーケット|カウントダウン|初詣|例大祭|縁日).*(?:終了しており|終了済み|期間外|開催されてい(?:た|ました)|対象外|見られません|間に合いません|過ぎて(?:おり|い)ます).*', re.IGNORECASE),
        re.compile(r'^[※*・\-\s]*(?:注意点|⚠️).*(?:終了|期間外|対象外).*', re.IGNORECASE),
    ]

    for line in lines:
        stripped = line.strip()
        if any(pat.match(stripped) for pat in out_of_period_patterns):
            logger.info(f"🧹 期間外イベントの余計な言及行を除去しました: {stripped}")
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def verify_maintenance_date_relevance(
    text: str,
    source_text: Optional[str] = None,
    user_input: Optional[str] = None
) -> str:
    """
    工事・休業・メンテナンス期間の日付比較・旅行日程重複検証フィルター：
    具体的な工事・休業期間（例: 7/13〜7/15）がユーザーの訪問・旅行日程（例: 7/19〜7/20）と
    重複していない場合、「工事中で利用できない」という誤警報・誤断定を正確な日付関係表現へ補正する。
    """
    if not text or not isinstance(text, str):
        return text

    # 工事・メンテナンス・休業等の利用制限への言及がない場合はそのまま返す
    if not any(kw in text for kw in ["工事", "メンテナンス", "休業", "利用できません", "ご利用できません", "利用不可"]):
        return text

    ctx_search = (source_text or "") + "\n" + text
    date_range_pattern = re.compile(
        r'(\d{1,2})\s*[月/]\s*(\d{1,2})\s*日?\s*(?:[\(（][月火水木金土日][\)）])?\s*[〜～~\-–—]\s*(?:(\d{1,2})\s*[月/]\s*)?(\d{1,2})\s*日?\s*(?:[\(（][月火水木金土日][\)）])?'
    )

    # 1. ユーザー旅行日程の抽出
    trip_start, trip_end = None, None
    if user_input:
        trip_matches = date_range_pattern.findall(user_input)
        if trip_matches:
            m1, d1, m2, d2 = trip_matches[0]
            trip_start = (int(m1), int(d1))
            trip_end = (int(m2) if m2 else int(m1), int(d2))

    if not trip_start:
        return text

    # 2. 工事・メンテナンス期間の抽出
    m_matches = date_range_pattern.findall(ctx_search)
    m_start, m_end = None, None
    for m1, d1, m2, d2 in m_matches:
        cand_start = (int(m1), int(d1))
        cand_end = (int(m2) if m2 else int(m1), int(d2))
        if cand_start == trip_start and cand_end == trip_end:
            continue
        m_start, m_end = cand_start, cand_end
        break

    if not m_start or not m_end:
        return text

    # 3. 日程の重複判定（m_end < trip_start または m_start > trip_end なら重複なし）
    if m_end < trip_start or m_start > trip_end:
        lines = text.splitlines()
        cleaned = []
        replaced = False
        for line in lines:
            if any(kw in line for kw in ["利用できません", "ご利用できません", "利用不可", "工事中"]) and any(kw in line for kw in ["プール", "工事", "メンテナンス", "休業"]):
                logger.info(f"🔧 工事期間({m_start[0]}/{m_start[1]}-{m_end[0]}/{m_end[1]})と旅行日程({trip_start[0]}/{trip_start[1]}-{trip_end[0]}/{trip_end[1]})の非重複を確認したため誤断定を是正しました")
                cleaned.append(
                    f"※ホテル公式サイト等の通知によるとメンテナンス工事期間は「{m_start[0]}月{m_start[1]}日〜{m_end[0]}月{m_end[1]}日」となっており、ご滞在予定の日程（{trip_start[0]}月{trip_start[1]}日〜{trip_end[0]}月{trip_end[1]}日）には影響なくご利用いただける見込みです（念のため最新状況は施設へご確認ください）。"
                )
                replaced = True
            else:
                cleaned.append(line)
        return "\n".join(cleaned)

    return text


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

    # 内部指示用語がそのまま見出し・セクションヘッダーとして漏洩するのを除去
    internal_heading_pattern = re.compile(
        r'^[#\s📌🔍💡]*(?:ソフトな確認|ソフト確認|確認事項|ヒアリング項目|内部メモ|指示メモ)\s*$',
        re.MULTILINE
    )
    text = internal_heading_pattern.sub('', text)

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


def verify_temporal_leadership_claims(text: str, source_text: str = "") -> str:
    """
    時代錯誤の役職・経営陣・政府要職ハルシネーション（古い事前学習データの記憶に基づくCEO・代表者・FRB議長等の誤り）を汎用的に検証・是正する。
    ソーステキスト（検索結果等）内の最新の人事情報と回答内容の乖離をチェックし、古い学習データを盲信した断言を防ぐ。
    """
    if not text:
        return text

    src = source_text or ""

    # 1. ソース中にウォーシュ新議長（Warsh）の記載がある、または2026年のFRB関連文脈でパウエル氏が誤って出力された場合の自動是正
    if any(w in src for w in ["ウォーシュ", "Warsh", "FRB", "Fed", "連邦準備制度"]):
        if any(p in text for p in ["パウエル", "Powell"]) and not any(p in src for p in ["パウエル", "Powell"]):
            logger.warning("[ExecutiveDefense] 事前学習データ起因の『FRBパウエル議長』ハルシネーションを検知しました → 『ウォーシュ新議長』または役職名のみへと是正")
            if any(w in src for w in ["ウォーシュ", "Warsh"]):
                text = re.sub(r'(?:FRB|連邦準備制度理事会)?パウエル(?:氏)?(?:FRB)?(?:議長|総裁)', 'FRBウォーシュ議長', text)
                text = re.sub(r'パウエル(?:氏)?(?:が|の|は)', 'ウォーシュ議長が', text)
                text = re.sub(r'Powell(?:\s*,\s*Fed\s*Chair)?', 'Kevin Warsh, Fed Chair', text)
            else:
                text = re.sub(r'(?:FRB|連邦準備制度理事会)?パウエル(?:氏)?(?:FRB)?(?:議長|総裁)', 'FRB議長', text)
                text = re.sub(r'パウエル(?:氏)?(?:が|の|は)', 'FRB議長が', text)

    if not src:
        return text

    titles = r'(?:CEO|社長|最高経営責任者|FRB議長|連邦準備制度理事会議長|議長|総裁|大統領|首相|財務長官|国務長官|会長|CFO|COO|代表取締役|知事|市長)'
    ceo_claims = re.findall(
        rf'([A-Z][a-zA-Z\s\.]+|[ぁ-んァ-ヶ亜-熙]+)(?:氏)?が(?:現)?{titles}|{titles}(?:の|である|：|:|で)?\s*([A-Z][a-zA-Z\s\.]+|[ぁ-んァ-ヶ亜-熙]+)(?:氏)?',
        text
    )
    if ceo_claims:
        for m in ceo_claims:
            person = (m[0] or m[1]).strip()
            if len(person) >= 2 and person not in src and person not in ["ウォーシュ", "Warsh", "米国", "日本", "同社", "当社", "政府"]:
                logger.warning(f"[ExecutiveDefense] ソース未確認または過去の役職者主張を検知・是正: {person}")
                # ソース本文に記載がない個人名を削除し、役職名（例：CEOやFRB議長）のみの記述へサニタイズ
                text = re.sub(rf'{re.escape(person)}(?:氏)?が(?:現)?({titles})', r'\1が', text)
                text = re.sub(rf'({titles})(?:の|である|：|:|で)?\s*{re.escape(person)}(?:氏)?', r'\1', text)

    return text


CHRONOLOGICAL_HEDGE_PATTERNS = [
    r"(?:(?:\d{4}年)?までとされていますが|在籍は[^。,\n]+までですが|脱退後も|退任後も|離脱後も|交代後も)[^。\n]*([^\n。]*(?:関わっ|参加|提供|収録|担当|共作|クレジット))",
    r"(?:リリースは[^。,\n]+年ですが|作品は[^。,\n]+年のものですが)[^。\n]*([^\n。]*(?:在籍中|以前のメンバー|当時のボーカル|彼が))",
]


def verify_chronological_rationalization(text: str, source_text: str = "") -> str:
    """
    Type 3（時系列衝突の後付け合理化・縫い合わせ）を非破壊的に検証するガードレール。
    単純に禁止・削除したり主語交代を断定するのではなく、代替仮説を列挙して要検索・再検証を促す。
    """
    if not text or not isinstance(text, str):
        return text

    src = source_text or ""
    has_rationalization = False
    for pat in CHRONOLOGICAL_HEDGE_PATTERNS:
        if re.search(pat, text):
            has_rationalization = True
            break

    if has_rationalization:
        supportive_keywords = ["ゲスト", "脱退後", "退任後", "共作", "クレジット", "作詞", "作曲", "楽曲提供", "アーカイブ", "未発表", "在籍時"]
        is_supported_by_source = False
        if src:
            is_supported_by_source = any(kw in src for kw in supportive_keywords)

        if not is_supported_by_source:
            logger.warning("[ChronologicalDefense] ソース裏付けのない時系列不一致・後付け縫い合わせ（合理化）表現を検知しました → 代替仮説を列挙")
            if "⚠️ **[時系列不一致・要確認]**" not in text and "制作(作曲/クレジット)時期と発表(録音/リリース)時期が異なる可能性" not in text:
                hedge_note = (
                    "\n\n💡 **【時系列整合性の要確認ポイント】**\n"
                    "制作・発表時期と人物の在籍期間にタイムラグや矛盾が生じている可能性があります。断定する前に以下の代替仮説をご検討ください：\n"
                    "- **仮説1**: 制作（作曲/作詞/クレジット等）時期と、実際の発表（録音/リリース/発信等）時期が異なる可能性\n"
                    "- **仮説2**: 対象期間には後任者や別のメンバーが担当・収録していた可能性\n"
                    "- **仮説3**: 前提となる年号や在籍期間そのものがソース記事上で異なっている可能性"
                )
                text = f"⚠️ **[時系列不一致・要確認: 制作・在籍時期の整合性が未検証です]** {text}" + hedge_note

    return text


def sanitize_unverified_listings(items: list[dict]) -> list[dict]:
    """
    未確認店舗エンティティのリスト（構造化データ）を処理し、
    完全削除ではなく属性情報のみの縮退表示候補へと変換する。
    """
    result = []
    for item in items:
        if item.get("name_verified", True) and not any(m in str(item.get("name", "")) for m in [
            "未確認", "未詳", "不明", "非公開"
        ]):
            result.append(item)
        else:
            loc = item.get("location", "") or item.get("address", "") or "該当エリア"
            desc = item.get("description", "") or item.get("feature", "") or "候補店舗"
            result.append({
                "name": None,
                "display": f"{loc}にある{desc}（※店名は未確認です。後ほど詳細を検索して確定できます）",
                "verified": False,
            })
    return result


def filter_unknown_entity_listings(text: str) -> str:
    """
    「3. ペリーロードの老舗イタリアン（※具体的な店舗名は未確認）」等の
    具体的な店舗名や正式名称が確認できていない不完全なエンティティが
    おすすめリストや箇条書き候補に混入した際、完全削除ではなく
    「縮退表示（検証ステータス付き）」へと非破壊的に変換するフィルター。
    """
    if not text or not isinstance(text, str):
        return text

    unconfirmed_markers = [
        "店舗名は未確認", "店名は未確認", "店名未詳", "具体的な店舗名は未確認",
        "名称は未確認", "名称未詳", "名称不明", "店名不明", "店舗名非公開",
        "具体的な名称は未確認", "名前は未確認", "店舗名未詳",
    ]
    if not any(marker in text for marker in unconfirmed_markers):
        return text

    lines = text.splitlines()
    cleaned_lines = []
    list_header_pattern = re.compile(r'^(\s*(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+[\.、\)]|[-・\*＋+])\s*)(.*?)$')

    for line in lines:
        match = list_header_pattern.match(line)
        if match:
            prefix, content = match.group(1), match.group(2)
            if any(marker in content for marker in unconfirmed_markers):
                logger.warning(f"[EntityListingDefense] 未確認店舗・名称未詳のリスト項目を縮退表示にリライトしました: {line[:50]}")
                clean_title = content
                for marker in unconfirmed_markers:
                    clean_title = re.sub(rf'[（\(]\s*※?\s*具体的な?{marker}\s*[）\)]', '', clean_title)
                    clean_title = re.sub(rf'[（\(]\s*※?\s*{marker}\s*[）\)]', '', clean_title)
                clean_title = clean_title.strip()
                cleaned_lines.append(f"{prefix}【店名要確認】{clean_title}（※具体的な店名は未確認です。後ほど検索して確定できます）")
                continue

        cleaned_line = line
        for marker in unconfirmed_markers:
            if marker in cleaned_line and not cleaned_line.strip().startswith("【店名要確認】"):
                cleaned_line = re.sub(rf'[（\(]\s*※?\s*具体的な?{marker}\s*[）\)]', '（※店名要確認）', cleaned_line)
                cleaned_line = re.sub(rf'[（\(]\s*※?\s*{marker}\s*[）\)]', '（※店名要確認）', cleaned_line)
        cleaned_lines.append(cleaned_line)

    return "\n".join(cleaned_lines)


def sanitize_buffer_contamination(text: str) -> str:
    """
    回答末尾や行中に混入した内部バッファの断片（思考ログ残骸、過去エラーログ、
    「②あいまいな回答...」「①問題点...」等の分析テキスト漏洩）を除去するサニタイザー。
    """
    if not text or not isinstance(text, str):
        return text

    patterns = [
        r'(?:\n|\s)*(?:①|②|③|④|⑤)\s*(?:あいまいな回答|問題点|対策|不確実性|思考ログ|ハルシネーション).*$',
        r'(?:\n|\s)*【(?:内部ログ|思考分析|プロンプト残骸|システム通知)】.*$',
    ]
    for pat in patterns:
        text = re.sub(pat, '', text, flags=re.DOTALL)

    return text.strip()


def enforce_variable_numerical_claims(text: str, source_text: str) -> str:
    """
    時間・金額・頻度・日付・件数などの「変動しうる数値情報」を検証・制御するフィルター。
    モデルの知識・推測を使用させず、検索結果からの直接コピーのみ許可する方針をプログラム的に担保する。

    【重要な設計方針変更】
    未検証の数値情報を検知した場合、以前はインラインで「※正確な〜」に置換していたが、
    同一回答内で何度もインライン注記が挿入されると視認性が著しく低下するため、
    未検証の数値はそのまま残しつつ検知カウントだけ記録し、回答末尾に一括で
    免責注記を1つだけ付与する方式に変更した。

    判定は完全一致および正規化形式。部分一致（"15"が共通してるからOK等）は行わない。
    """
    if not text:
        return text

    src = source_text or ""
    unverified_categories: set[str] = set()

    # ====================================================================
    # 1. 時間間隔・頻度（例: 「30分毎」「30分ごと」「30分に1本」「1時間おき」等）
    # ====================================================================
    def _check_frequency(match):
        claim = match.group(0)
        if claim in src:
            return claim
        logger.warning(f"[NumericalDefense] ソース未記載の運行頻度・間隔の生成を検知: {claim}")
        unverified_categories.add("運行間隔")
        return claim  # そのまま残す

    text = re.sub(
        r'\d+分(?:毎|ごと|おき|間隔|に1本)|\d+時間(?:毎|ごと|おき|間隔|に1本)',
        _check_frequency,
        text
    )

    # ====================================================================
    # 2. 便数・本数（例: 「1日4便」「4便運行」等）
    # ====================================================================
    def _check_transport_count(match):
        claim = match.group(0)
        if claim in src:
            return claim
        logger.warning(f"[NumericalDefense] ソース未記載の便数・本数を検知: {claim}")
        unverified_categories.add("便数")
        return claim

    text = re.sub(r'1日\d+(?:便|本|往復)', _check_transport_count, text)

    # ====================================================================
    # 3. 移動・アクセス所要時間（例: 「車約20分」「徒歩約10分」等）
    # ====================================================================
    def _check_travel_time(match):
        claim = match.group(0)
        if claim in src:
            return claim
        num_match = re.search(r'\d+', claim)
        if num_match:
            mins = num_match.group(0)
            if f"{mins}分" in src:
                return claim
        logger.warning(f"[NumericalDefense] ソース未記載の所要時間を検知: {claim}")
        unverified_categories.add("所要時間")
        return claim

    text = re.sub(
        r'(?:車|徒歩|バス|電車|タクシー)(?:で)?(?:約)?\d+分',
        _check_travel_time,
        text
    )

    # ====================================================================
    # 4. 時間帯レンジ（例: 「14:00〜17:40の間」「9時〜17時」等）
    # ====================================================================
    def _check_time_range(match):
        claim = match.group(0)
        if claim in src:
            return claim
        # HH:MM または X時(Y分) を検証
        times_hhmm = re.findall(r'\d{1,2}:\d{2}', claim)
        times_jp = re.findall(r'\d{1,2}時(?:\d{1,2}分)?', claim)
        times = times_hhmm + times_jp
        if times and all(t in src for t in times):
            return claim
        logger.warning(f"[NumericalDefense] ソース未記載の時間帯レンジを検知: {claim}")
        unverified_categories.add("営業時間")
        return claim

    text = re.sub(
        r'(?:\d{1,2}:\d{2}|\d{1,2}時(?:\d{1,2}分)?)\s*[〜~\-－]\s*(?:\d{1,2}:\d{2}|\d{1,2}時(?:\d{1,2}分)?)(?:の間)?',
        _check_time_range,
        text
    )

    # ====================================================================
    # 5. 単独時刻の捏造検知（例: 「15:30発」「15時30分発」「15:30の」等）
    # ====================================================================
    _SERVICE_CONTEXT_KEYWORDS = [
        "発", "着", "便", "本", "運行", "送迎", "シャトル", "バス", "出発",
        "到着", "営業", "開館", "閉館", "開店", "閉店", "受付", "チェックイン",
        "チェックアウト", "最終", "始発", "終電", "乗車",
    ]

    def _check_standalone_time(match):
        claim_time = match.group(1)
        full_match = match.group(0)

        if claim_time in src:
            return full_match

        start = max(0, match.start() - 30)
        end = min(len(text), match.end() + 30)
        context_window = text[start:end]
        is_service_context = any(kw in context_window for kw in _SERVICE_CONTEXT_KEYWORDS)

        if not is_service_context:
            return full_match

        logger.warning(f"[NumericalDefense] ソース未記載の単独時刻を検知: {claim_time}")
        unverified_categories.add("営業時間")
        return full_match

    text = re.sub(
        r'(\d{1,2}:\d{2}|\d{1,2}時\d{1,2}分)\s*(?:発|着|便|頃|から|まで|～|〜|の)',
        _check_standalone_time,
        text
    )

    # ====================================================================
    # 6. 料金・価格（例: 「2,500円」「1,500円」等）
    # ====================================================================
    def _check_price(match):
        price_str = match.group(0)
        num_only = price_str.replace(",", "")
        val_str = re.sub(r'[^0-9]', '', price_str)
        if price_str in src or num_only in src:
            return price_str
        if val_str and (f"{val_str}円" in src or f"{int(val_str):,}" in src or f"￥{val_str}" in src or f"¥{val_str}" in src or (len(val_str) >= 3 and val_str in src)):
            return price_str
        logger.warning(f"[NumericalDefense] ソース未記載の料金・金額を検知: {price_str}")
        unverified_categories.add("料金")
        return price_str

    text = re.sub(r'\d+(?:,\d+)*円', _check_price, text)

    # ====================================================================
    # 7. イベント・施設開始日程（例: 「7月15日から海開き」等）
    # ====================================================================
    def _check_date_claim(match):
        date_str = match.group(1)
        full_match = match.group(0)
        if date_str in src or full_match in src:
            return full_match

        start = max(0, match.start() - 25)
        end = min(len(text), match.end() + 25)
        context_window = text[start:end]
        event_kws = ["海開き", "開催", "オープン", "開始", "営業期間"]
        if any(kw in context_window for kw in event_kws):
            logger.warning(f"[NumericalDefense] ソース未記載のイベント開始日を検知: {date_str}")
            unverified_categories.add("日程")
        return full_match

    text = re.sub(
        r'(\d{1,2}月\d{1,2}日)\s*(?:から|より)',
        _check_date_claim,
        text
    )

    # ====================================================================
    # 8. 統計・パーセンテージ（例: 「70%」「39.5%」「7割」等）
    # ====================================================================
    def _check_percentage_claim(match):
        pct_str = match.group(0)
        num_part = match.group(1)
        if pct_str in src or num_part in src:
            return pct_str
        logger.warning(f"[NumericalDefense] ソース未記載のパーセンテージ・統計比率を検知: {pct_str}")
        unverified_categories.add("統計比率")
        return pct_str

    text = re.sub(r'(\d+(?:\.\d+)?)(?:%|％|割)', _check_percentage_claim, text)

    # ====================================================================
    # 末尾一括注記: 未検証カテゴリが1つ以上ある場合のみ追加
    # ただし金融・政治経済・ニュース分析系の回答には旅行向け免責注記を付けない
    # ====================================================================
    if unverified_categories:
        categories_str = "・".join(sorted(unverified_categories))

        # 回答コンテキストの判定: 金融・市場・政治経済系のキーワードが優勢かどうか
        _FINANCE_NEWS_KEYWORDS = [
            "株価", "日経平均", "TOPIX", "S&P", "NASDAQ", "ダウ", "原油", "WTI", "ブレント",
            "為替", "ドル円", "金利", "利回り", "先物", "市場", "相場", "投資", "銘柄",
            "封鎖", "空爆", "制裁", "停戦", "紛争", "危機", "地政学", "ホルムズ",
            "GDP", "インフレ", "CPI", "FRB", "日銀", "金融政策", "利上げ", "利下げ",
            "決算", "業績", "収益", "売上", "時価総額", "PER", "配当",
        ]
        _TRAVEL_SPOT_KEYWORDS = [
            "ホテル", "旅館", "レストラン", "カフェ", "観光", "ビーチ", "水族館",
            "温泉", "散策", "ランチ", "ディナー", "食べログ", "チェックイン",
            "アクセス", "徒歩", "シャトルバス", "ロープウェイ", "お土産",
            "ペリーロード", "プリンスホテル", "海水浴", "お出かけ",
        ]
        finance_score = sum(1 for kw in _FINANCE_NEWS_KEYWORDS if kw in text)
        travel_score = sum(1 for kw in _TRAVEL_SPOT_KEYWORDS if kw in text)
        is_finance_context = finance_score >= 3 and finance_score > travel_score

        if is_finance_context:
            logger.info(f"[NumericalDefense] 金融・ニュース分析コンテキスト検出(finance={finance_score}, travel={travel_score}) → アナリスト向けデータ注記判定")
            if "統計比率" in unverified_categories and "※一部の比率" not in text:
                text = text.rstrip() + "\n\n※一部の比率・市場指標はソース記事に明記されていない推計または周辺参考データを含む場合があります。正確な数値は公式開示データをご確認ください。"
        elif travel_score > 0 or any(cat in unverified_categories for cat in ["営業時間", "料金", "便数", "運行間隔", "日程"]):
            logger.info(f"[NumericalDefense] 店舗・旅行・サービスお出かけコンテキスト検出(travel={travel_score}, categories={categories_str}) → 末尾一括注記を追加")
            if "※営業時間" not in text and "※正確な" not in text and "※最新の情報" not in text and "※お出かけ前に" not in text:
                text = text.rstrip() + f"\n\n※{categories_str}等の情報は変動する場合があります。お出かけ前に公式サイトや店舗へ直接ご確認いただくことをおすすめします。"
        elif "統計比率" in unverified_categories and len(unverified_categories) == 1:
            logger.info("[NumericalDefense] 一般・雑談文脈における統計比率のみの未検証検出 → 見当違いな店舗免責注記不要としてスキップ")
        else:
            logger.info(f"[NumericalDefense] 一般文脈における未検証数値カテゴリ({categories_str}) → 汎用免責注記")
            if "※正確な" not in text and "※最新の情報" not in text and "※各種情報" not in text:
                text = text.rstrip() + f"\n\n※{categories_str}等の情報は参考値または変動する場合があります。最新の情報は各公式サイト等をご確認ください。"

    return check_financial_arithmetic_consistency(text)


def check_financial_arithmetic_consistency(text: str) -> str:
    """
    株価・指数に関する記述で、同一回答内における価格差と変動幅の算術的矛盾を検知・警告する。
    例: 安値66,653円・寄り68,410円（差額1,757円）とあるのに「一時2,500円超下落」のように矛盾する数値が記載されている場合。
    """
    if not text:
        return text

    # 日経平均等の数値が複数あり、さらに「〇〇円（超）下落/安」などの変動幅があるかチェック
    drop_match = re.search(r'一時([0-9,]+)円(?:超|余り)?(?:下落|安)', text)
    if not drop_match:
        return text

    try:
        drop_claimed = int(drop_match.group(1).replace(",", ""))
        # 5万〜8万円帯の日経平均価格候補を取得
        prices = [int(p.replace(",", "")) for p in re.findall(r'(6[0-9],[0-9]{3}|7[0-9],[0-9]{3}|5[0-9],[0-9]{3})円', text)]
        if len(prices) >= 2:
            max_diff = max(prices) - min(prices)
            # 実際の価格レンジ差と主張された一時下落幅が500円以上の乖離を持つ場合にアラート
            if drop_claimed > max_diff + 500 and "※【数値整合性アラート】" not in text:
                logger.warning(f"[FinancialDefense] 算術不整合検知: 価格帯差額 {max_diff}円 vs 主張下落幅 {drop_claimed}円")
                text = text.rstrip() + f"\n\n※【数値整合性アラート】文中で言及された価格帯の差額（約{max_diff:,}円）と、一時変動幅（{drop_claimed:,}円）の間に算術的な乖離が生じています。各時間帯の公式取引データをご確認ください。"
    except Exception as e:
        logger.debug(f"[FinancialDefense] 算術チェック時スキップ: {e}")

    return text



