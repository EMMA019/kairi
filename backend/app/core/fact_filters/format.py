import re
from datetime import date, timedelta
from typing import Optional
from app.utils.logger import get_logger
from app.core.source_evaluator import verify_entity_claim_attribution

logger = get_logger(__name__)



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

