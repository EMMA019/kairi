"""
検索結果の単純リランカー（キーワードベース ＋ 品質スコアリング ＋ 重複排除）
セマンティックベクトルは使わず、クエリとのキーワード一致率、ドメイン信頼度、Jaccard係数による重複排除を組み合わせたスコアリング。
重み: タイトル一致=10点, URL一致=5点, スニペット内キーワード一致=2点
"""
import re
from urllib.parse import urlparse
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 高品質ドメイン（加点対象）
HIGH_QUALITY_DOMAINS = {
    "reuters.com": 30.0,
    "bloomberg.com": 30.0,
    "nikkei.com": 30.0,
    "wsj.com": 30.0,
    "cnbc.com": 30.0,
    "ft.com": 30.0,
    "bloomberg.co.jp": 30.0,
    "jp.reuters.com": 30.0,
    "investing.com": 20.0,
    "finance.yahoo.com": 15.0,
    "bbc.com": 20.0,
    "cnn.com": 20.0,
    "nhk.or.jp": 20.0,
}

# 低品質・スパム・まとめドメイン（減点対象）
LOW_QUALITY_DOMAINS = {
    "yahoo.co.jp": -10.0, # アグリゲーションサイト
    "msn.com": -10.0,     # アグリゲーションサイト
    "5ch.net": -30.0,
    "togetter.com": -20.0,
    "livedoor.jp": -15.0,
    "prtimes.jp": -5.0,   # プレスリリースより一次報道を優先
}


def _tokenize(text: str) -> set[str]:
    """テキストをトークン分割してセットで返す"""
    text_lower = text.lower()
    words = set(re.findall(r'[a-z0-9]+', text_lower))
    
    jp_chars = re.findall(r'[\u3040-\u9fff]+', text)
    for jp in jp_chars:
        for i in range(len(jp) - 1):
            words.add(jp[i:i+2])
    
    return words


def _get_domain_score(url: str) -> float:
    """URLからドメインを抽出し、品質スコアを返す"""
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        
        for hq_domain, score in HIGH_QUALITY_DOMAINS.items():
            if domain == hq_domain or domain.endswith("." + hq_domain):
                return score
        
        for lq_domain, score in LOW_QUALITY_DOMAINS.items():
            if domain == lq_domain or domain.endswith("." + lq_domain):
                return score
    except Exception:
        pass
    return 0.0


def _calculate_jaccard_similarity(tokens1: set[str], tokens2: set[str]) -> float:
    """Jaccard係数で類似度を計算（0.0 〜 1.0）"""
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union


def rerank(query: str, results: list[dict], top_k: int = 10, threshold: float = 0.0) -> list[dict]:
    """
    検索結果をキーワード一致率＋ドメイン品質でスコアリングして並べ替え、
    類似する重複記事を排除（Deduplication）して返す。
    """
    if not results or len(results) <= 1:
        return results

    try:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return results[:top_k]

        # 1. 各記事の基礎スコアリング
        scored = []
        for item in results:
            score = 0.0
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            
            title_tokens = _tokenize(title)
            snippet_tokens = _tokenize(snippet)
            url_tokens = _tokenize(url)
            
            # キーワード一致スコア
            score += len(query_tokens & title_tokens) * 10.0
            score += len(query_tokens & url_tokens) * 5.0
            score += len(query_tokens & snippet_tokens) * 2.0
            
            # 完全一致ボーナス
            query_lower = query.lower()
            if query_lower in title.lower():
                score += 20.0
            if query_lower in snippet.lower():
                score += 10.0
                
            # ドメイン品質スコア
            score += _get_domain_score(url)
            
            scored.append((score, item, title_tokens | snippet_tokens))
        
        # 2. スコア降順でソート
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 3. 重複排除（Deduplication）
        deduplicated = []
        seen_tokens_list = []
        
        for score, item, item_tokens in scored:
            is_duplicate = False
            for seen_tokens in seen_tokens_list:
                sim = _calculate_jaccard_similarity(item_tokens, seen_tokens)
                # 60%以上のトークン一致は重複とみなす
                if sim > 0.6:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(item)
                seen_tokens_list.append(item_tokens)
                
            if len(deduplicated) >= top_k:
                break
        
        top_score = scored[0][0] if scored else 0
        logger.info(f"リランキング完了: {len(results)}件 → {len(deduplicated)}件 (重複排除済) / 最高スコア: {top_score:.1f}")
        
        return deduplicated

    except Exception as e:
        logger.error(f"リランキングに失敗しました: {e}")
        return results[:top_k]