"""
Search client abstraction.

Tavily stays the primary provider, but the rest of the app should not care
which provider produced the results.
"""
import asyncio
import logging

from app.core.config import get_settings
from app.search.google_news import search_google_news
from app.search.tavily_client import search as search_tavily

logger = logging.getLogger(__name__)
settings = get_settings()

PROVIDERS = {
    "google_news": search_google_news,
    "tavily": search_tavily,
}


def _provider_chain() -> list[str]:
    providers: list[str] = []
    for name in (settings.search_provider, settings.search_fallback_provider):
        normalized = (name or "").strip().lower()
        if normalized and normalized not in providers:
            providers.append(normalized)
    return providers or ["tavily"]


async def search(query: str, max_results: int = 5, days: int = 30) -> list[dict]:
    last_error: Exception | None = None

    for provider_name in _provider_chain():
        provider = PROVIDERS.get(provider_name)
        if provider is None:
            logger.warning("Unknown search provider configured: %s", provider_name)
            continue

        try:
            results = await provider(query=query, max_results=max_results, days=days)
            if not results:
                continue

            for item in results:
                item.setdefault("provider", provider_name)

            return results
        except Exception as exc:
            last_error = exc
            logger.warning("Search provider %s failed for '%s...': %s", provider_name, query[:50], exc)

    if last_error:
        logger.warning("All search providers failed for '%s...'", query[:50])
    return []


async def search_batch(queries: list[str], max_results: int = 5, days: int = 30) -> dict[str, list[dict]]:
    semaphore = asyncio.Semaphore(max(1, settings.search_max_concurrency))

    async def _run(query: str) -> tuple[str, list[dict]]:
        async with semaphore:
            return query, await search(query, max_results=max_results, days=days)

    return dict(await asyncio.gather(*(_run(query) for query in queries)))


def format_results(results: list[dict]) -> str:
    if not results:
        return "Žádné výsledky nenalezeny."

    parts: list[str] = []
    for i, result in enumerate(results, 1):
        title = result.get("title", "Bez názvu")
        url = result.get("url", "")
        content = (result.get("content", "") or "").strip()[:300]
        provider = result.get("provider", "")
        provider_suffix = f" [{provider}]" if provider else ""
        parts.append(f"[{i}] {title}{provider_suffix}\nURL: {url}\n{content}")
    return "\n\n---\n\n".join(parts)
