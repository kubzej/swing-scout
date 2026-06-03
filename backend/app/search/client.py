"""
Search client abstraction.

Tavily stays the primary provider, but the rest of the app should not care
which provider produced the results.
"""
import asyncio
import logging
from time import perf_counter

from app.core.config import get_settings
from app.core.run_logging import log_event
from app.search.google_news import search_google_news
from app.search.tavily_client import search as search_tavily

logger = logging.getLogger(__name__)
settings = get_settings()

PROVIDERS = {
    'google_news': search_google_news,
    'tavily': search_tavily,
}


def _provider_chain() -> list[str]:
    providers: list[str] = []
    for name in (settings.search_provider, settings.search_fallback_provider):
        normalized = (name or '').strip().lower()
        if normalized and normalized not in providers:
            providers.append(normalized)
    return providers or ['tavily']


async def search(query: str, max_results: int = 5, days: int = 30) -> list[dict]:
    last_error: Exception | None = None
    provider_chain = _provider_chain()
    log_event(
        logger,
        logging.INFO,
        'search_started',
        query=query[:80],
        max_results=max_results,
        days=days,
        providers=provider_chain,
    )

    for provider_name in provider_chain:
        provider = PROVIDERS.get(provider_name)
        if provider is None:
            logger.warning('Unknown search provider configured: %s', provider_name)
            continue

        start = perf_counter()
        try:
            results = await provider(query=query, max_results=max_results, days=days)
            if not results:
                log_event(
                    logger,
                    logging.INFO,
                    'search_provider_empty',
                    provider=provider_name,
                    query=query[:80],
                    duration_ms=round((perf_counter() - start) * 1000),
                )
                continue

            for item in results:
                item.setdefault('provider', provider_name)

            log_event(
                logger,
                logging.INFO,
                'search_provider_completed',
                provider=provider_name,
                query=query[:80],
                results=len(results),
                duration_ms=round((perf_counter() - start) * 1000),
            )
            return results
        except Exception as exc:
            last_error = exc
            log_event(
                logger,
                logging.WARNING,
                'search_provider_failed',
                provider=provider_name,
                query=query[:80],
                duration_ms=round((perf_counter() - start) * 1000),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            logger.warning("Search provider %s failed for '%s...': %s", provider_name, query[:50], exc)

    if last_error:
        log_event(logger, logging.WARNING, 'search_all_providers_failed', query=query[:80])
    return []


async def search_batch(queries: list[str], max_results: int = 5, days: int = 30) -> dict[str, list[dict]]:
    semaphore = asyncio.Semaphore(max(1, settings.search_max_concurrency))

    async def _run(query: str) -> tuple[str, list[dict]]:
        async with semaphore:
            return query, await search(query, max_results=max_results, days=days)

    return dict(await asyncio.gather(*(_run(query) for query in queries)))


def format_results(results: list[dict]) -> str:
    if not results:
        return 'Zadne vysledky nenalezeny.'

    parts: list[str] = []
    for i, result in enumerate(results, 1):
        title = result.get('title', 'Bez nazvu')
        url = result.get('url', '')
        content = (result.get('content', '') or '').strip()[:300]
        provider = result.get('provider', '')
        provider_suffix = f' [{provider}]' if provider else ''
        parts.append(f'[{i}] {title}{provider_suffix}\nURL: {url}\n{content}')
    return '\n\n---\n\n'.join(parts)
