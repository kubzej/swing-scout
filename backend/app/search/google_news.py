"""
Google News RSS fallback provider.

Lower quality than Tavily, but good enough as a safety net when the main
provider is unavailable or over quota.
"""
from html import unescape
import logging
import re
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
REQUEST_TIMEOUT = 20
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(HTML_TAG_RE.sub("", text or "")).strip()


async def search_google_news(query: str, max_results: int = 5, days: int = 30) -> list[dict]:
    recent_query = f"{query} when:{days}d" if days and days <= 30 else query
    encoded_query = quote_plus(recent_query)
    url = f"{GOOGLE_NEWS_URL}?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "SwingScout/1.0"})
        response.raise_for_status()

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError as exc:
        logger.warning("Google News RSS parse failed for '%s...': %s", query[:50], exc)
        return []

    results: list[dict] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = _strip_html(item.findtext("description") or "")
        pub_date = (item.findtext("pubDate") or "").strip()

        if not title:
            continue

        results.append({
            "title": title,
            "url": link,
            "content": description,
            "published_at": pub_date,
            "provider": "google_news",
        })
        if len(results) >= max_results:
            break

    return results
