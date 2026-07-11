"""
検索結果の単純リランカー（キーワードベース）
セマンティックベクトルは使わず、クエリとのキーワード一致率でスコアリング。
重み: タイトル一致=10点, URL一致=5点, スニペット内キーワード一致=2点
"""
import re
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _tokenize(text: str) -> set[str]:
    """テキストをトークン分割してセットで返す"""
    # 英語: 小文字にして単語分割
    # 日本語: 2文字以上のn-gramで近似
    text_lower = text.lower()
    
    # 英単語トークン
    words = set(re.findall(r'[a-z0-9]+', text_lower))
    
    # 日本語: 2-gram
    jp_chars = re.findall(r'[\u3040-\u9fff]+', text)
    for jp in jp_chars:
        for i in range(len(jp) - 1):
            words.add(jp[i:i+2])
    
    return words


def rerank(query: str, results: list[dict], top_k: int = 10, threshold: float = 0.0) -> list[dict]:
    """
    検索結果をキーワード一致率でスコアリングして並べ替え。
    全ての結果を返す（閾値なし）。
    """
    if not results or len(results) <= 1:
        return results

    try:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return results[:top_k]

        scored = []
        for item in results:
            score = 0.0
            
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            
            title_tokens = _tokenize(title)
            snippet_tokens = _tokenize(snippet)
            url_tokens = _tokenize(url)
            
            # タイトル一致: 1トークン=10点
            title_match = len(query_tokens & title_tokens)
            score += title_match * 10.0
            
            # URL一致: 1トークン=5点
            url_match = len(query_tokens & url_tokens)
            score += url_match * 5.0
            
            # スニペット一致: 1トークン=2点
            snippet_match = len(query_tokens & snippet_tokens)
            score += snippet_match * 2.0
            
            # 完全一致ボーナス: クエリ全文がタイトル/スニペットに含まれていたら+20
            query_lower = query.lower()
            if query_lower in title.lower():
                score += 20.0
            if query_lower in snippet.lower():
                score += 10.0
            
            scored.append((score, item))
        
        # スコア降順でソート
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 全件返す（スコア付き）
        reranked = [item for _, item in scored]
        
        top_score = scored[0][0] if scored else 0
        logger.info(f"リランキング完了: {len(results)}件→スコア範囲: 0〜{top_score:.1f}")
        
        return reranked[:top_k]

    except Exception as e:
        logger.error(f"リランキングに失敗しました: {e}")
        return results[:top_k]