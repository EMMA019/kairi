import httpx
import os
from app.utils.logger import get_logger

logger = get_logger(__name__)

def _smart_academic_extract(text: str, max_chars: int = 25000) -> str:
    """学術論文から冒頭部およびDefense Mechanism/実験表/結論など後半セクションを優先抽出"""
    if not text or len(text) <= max_chars:
        return text
    head = text[:8000]
    tail = text[-17000:]
    return head + "\n\n[...論文中間部（一部数式等）省略...]\n\n" + tail


async def fetch_with_jina(url: str) -> str:
    """
    Jina AI Reader公式API。
    任意のURLからクリーンなテキストを取得。
    """
    JINA_API_KEY = os.environ.get("JINA_API_KEY")
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/plain"}
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    try:
        from .http_client import get_http_client
        client = get_http_client()
        res = await client.get(jina_url, headers=headers, timeout=15)
        res.raise_for_status()
        raw_text = res.text
        
        import re
        text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        return _smart_academic_extract(text)
    except Exception as e:
        logger.warning(f"Jina AI Reader取得エラー (URL: {url}): {e} -> 直接HTTPスクレイピングにフォールバックします")
        return await fetch_direct_html(url)


from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

async def _can_fetch_robots(url: str, user_agent: str = "*") -> bool:
    """対象サイトのrobots.txtを遵守しスクレイピング許可・禁止状況を確認する"""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        from .http_client import get_http_client
        client = get_http_client()
        res = await client.get(robots_url, timeout=5)
        if res.status_code == 200:
            rp = RobotFileParser()
            rp.parse(res.text.splitlines())
            allowed = rp.can_fetch(user_agent, url)
            if not allowed:
                logger.warning(f"robots.txt によりスクレイピング禁止エリアと判定されました: {url}")
            return allowed
    except Exception:
        pass
    return True


async def fetch_direct_html(url: str) -> str:
    """Jina失敗時の直接HTTP+HTMLテキストスクレイピングフォールバック (robots.txt厳守)"""
    try:
        from .http_client import get_http_client
        import re
        
        # --- 🛡️ robots.txt マナー遵守チェック ---
        if not await _can_fetch_robots(url):
            logger.warning(f"robots.txt 遵守のため直接フェッチをスキップします: {url}")
            return ""

        client = get_http_client()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        res = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
        res.raise_for_status()
        html = res.text

        # <script>, <style> タグなどの非表示領域を削除
        html = re.sub(r'<script[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<style[\s\S]*?</style>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<header[\s\S]*?</header>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<footer[\s\S]*?</footer>', '', html, flags=re.IGNORECASE)

        # HTMLタグの除去とテキスト抽出
        text = re.sub(r'<[^>]+>', ' ', html)
        # 空行や余分なスペースの整理
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        full_text = "\n".join(lines)
        clean_text = _smart_academic_extract(full_text)
        logger.info(f"直接HTTPスクレイピング成功: {url} ({len(clean_text)}文字)")
        return clean_text
    except Exception as e2:
        logger.error(f"直接HTTPスクレイピングも失敗 (URL: {url}): {e2}")
        return ""

