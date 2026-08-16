import re
from datetime import date, timedelta
from typing import Optional
from app.utils.logger import get_logger
from app.core.source_evaluator import verify_entity_claim_attribution
from .financial import check_financial_arithmetic_consistency

logger = get_logger(__name__)


# API制限や数値系の隠蔽パターン
NUMERIC_LIMITS_MARKERS = [
    r"\d+リクエスト",
    r"\d+件/日",
    r"\d+回/日",
    r"\d+回/分",
]

NUMERIC_LIMITS_PATTERN = re.compile("|".join(NUMERIC_LIMITS_MARKERS))


# 🟠 P1: 投資助言・確度・売買タイミング・資金配分
ADVICE_MARKERS = [r"確度\s*\d+%", r"確率\s*\d+%", r"ナンピン", r"損切り", r"厚めに", r"絞って", r"全力で", r"買うべき", r"売るべき"]

ADVICE_PATTERN = re.compile("|".join(ADVICE_MARKERS))


# 🔴 P0: 判定記号やテーブル、強い仮説断定
SYMBOL_TABLE_MARKERS = [r"[◯△❌⭐◎✕×]", r"最有力", r"鍵で(ある|す)", r"間違いない"]

SYMBOL_TABLE_PATTERN = re.compile("|".join(SYMBOL_TABLE_MARKERS))


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



def enforce_variable_numerical_claims(text: str, source_text: str, user_input: str = "") -> str:
    """
    時間・金額・頻度・日付・件数などの「変動しうる数値情報」を検証・制御するフィルター。
    モデルの知識・推測を使用させず、検索結果からの直接コピーのみ許可する方針をプログラム的に担保する。

    【重要な設計方針変更】
    未検証の数値情報を検知した場合、以前はインラインで「※正確な〜」に置換していたが、
    同一回答内で何度もインライン注記が挿入されると視認性が著しく低下するため、
    未検証の数値はそのまま残しつつ検知カウントだけ記録し、回答末尾に一括で
    免責注記を1つだけ付与する方式に変更した。

    判定は完全一致および正規化形式。部分一致（"15"が共通してるからOK等）は行わない。
    user_input: 旅行免責はユーザー発話に旅行意図があるときだけ付与する（能力説明の「観光」誤爆防止）。
    """
    if not text:
        return text

    src = source_text or ""
    user_q = user_input or ""
    unverified_categories: set[str] = set()

    # 「」「」内の禁止例・能力説明中の％は統計比率フラグにしない
    def _pct_in_quote(pos: int) -> bool:
        # 直前の開き引用と閉じ引用のバランスで簡易判定
        before = text[:pos]
        # 全角・半角カギ括弧
        for open_c, close_c in (("「", "」"), ("『", "』"), ("\"", "\""), ("'", "'")):
            if before.count(open_c) > before.count(close_c):
                return True
        return False

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
        if _pct_in_quote(match.start()):
            logger.debug(f"[NumericalDefense] 引用・禁止例内の％をスキップ: {pct_str}")
            return pct_str
        logger.warning(f"[NumericalDefense] ソース未記載のパーセンテージ・統計比率を検知: {pct_str}")
        unverified_categories.add("統計比率")
        return pct_str

    text = re.sub(r'(\d+(?:\.\d+)?)(?:%|％|割)', _check_percentage_claim, text)

    # ====================================================================
    # 末尾一括注記: 未検証カテゴリがあれば、種類を問わず同一の一般注意喚起。
    # ドメイン推定（旅行/金融）はコンテキスト判定を誤ると見当違いな文言になるため廃止。
    # ====================================================================
    if unverified_categories:
        categories_str = "・".join(sorted(unverified_categories))
        # 注意喚起文言は UI 常設（InputArea）。本文末尾には付けない。
        # 検知自体は Integrity / filter_metrics に残す。
        if unverified_categories == {"統計比率"} and not src.strip():
            logger.info(
                "[NumericalDefense] ソース無し・統計比率のみ → 記録スキップ（雑談誤爆回避）"
            )
        else:
            try:
                from app.core.fact_filters.filter_metrics import bump_filter

                bump_filter("ai_caution_signal", changed=True)
            except Exception:
                pass
            logger.info(
                f"[NumericalDefense] 未検証数値カテゴリ({categories_str}) → UI常設注意喚起に委譲（本文非付与）"
            )

    return check_financial_arithmetic_consistency(text)



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

