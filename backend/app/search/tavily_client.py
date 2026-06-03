"""
Tavily search client — web search for AI agent discovery and research.

Free tier: 1000 requests/month. Always be search-efficient — batch queries, cache results.
Requires: TAVILY_API_KEY env var.
"""
import asyncio
import logging
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_client = None
SEARCH_TIMEOUT = 30

FINANCIAL_DOMAINS = [
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "seekingalpha.com",
    "fool.com",
    "marketwatch.com",
    "businesswire.com",
    "prnewswire.com",
    "sec.gov",
    "finance.yahoo.com",
    "investing.com",
    "barrons.com",
]


def _get_client():
    global _client
    if _client is None:
        from tavily import TavilyClient
        if not settings.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is not set")
        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


async def search(query: str, max_results: int = 5, days: int = 30) -> list[dict]:
    def _sync_search():
        client = _get_client()
        result = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_raw_content=False,
            days=days,
            include_domains=FINANCIAL_DOMAINS,
        )
        if not result.get("results"):
            result = client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
                include_raw_content=False,
                days=days,
            )
        return result.get("results", [])

    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_search),
            timeout=SEARCH_TIMEOUT,
        )
        logger.info("Tavily: '%s...' → %d results", query[:50], len(results))
        return results
    except asyncio.TimeoutError:
        logger.warning("Tavily timed out for '%s'", query[:50])
        return []
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ("usage limit", "quota", "limit exceeded", "402")):
            logger.warning("Tavily rate limit reached: %s", e)
            raise ValueError("Překročen měsíční limit Tavily.")
        logger.error("Tavily search failed for '%s': %s", query[:50], e)
        return []


def format_results(results: list[dict]) -> str:
    if not results:
        return "Žádné výsledky nenalezeny."
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Bez názvu")
        url = r.get("url", "")
        content = r.get("content", "").strip()[:300]
        parts.append(f"[{i}] {title}\nURL: {url}\n{content}")
    return "\n\n---\n\n".join(parts)
