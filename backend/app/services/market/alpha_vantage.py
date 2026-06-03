"""
Alpha Vantage market movers provider.

Used as the primary Stage 1 discovery feed because it returns a provider-supplied
candidate list without relying on any hardcoded stock universe on our side.
"""
import json
import logging
from time import perf_counter

import httpx

from app.core.cache import CacheTTL
from app.core.config import get_settings
from app.core.run_logging import log_event

logger = logging.getLogger(__name__)
settings = get_settings()

ALPHA_VANTAGE_URL = 'https://www.alphavantage.co/query'
ALPHA_VANTAGE_TIMEOUT = 20
ALPHA_VANTAGE_DEMO_KEY = 'demo'


async def get_top_movers(redis) -> dict:
    cache_key = 'ss:alpha_vantage:top_movers'
    cached = await redis.get(cache_key)
    if cached:
        payload = json.loads(cached)
        log_event(
            logger,
            logging.INFO,
            'alpha_vantage_cache_hit',
            top_gainers=len(payload.get('top_gainers', [])),
            top_losers=len(payload.get('top_losers', [])),
            most_active=len(payload.get('most_actively_traded', [])),
        )
        return payload

    params = {
        'function': 'TOP_GAINERS_LOSERS',
        'apikey': settings.alpha_vantage_api_key or ALPHA_VANTAGE_DEMO_KEY,
    }
    log_event(logger, logging.INFO, 'alpha_vantage_request_started', demo_key=not bool(settings.alpha_vantage_api_key))
    start = perf_counter()

    async with httpx.AsyncClient(timeout=ALPHA_VANTAGE_TIMEOUT) as client:
        response = await client.get(ALPHA_VANTAGE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        logger.warning('Alpha Vantage returned non-dict payload')
        return {}

    if data.get('Error Message'):
        logger.warning('Alpha Vantage returned error: %s', data['Error Message'])
        return {}

    if data.get('Note') or data.get('Information'):
        logger.warning('Alpha Vantage note/info: %s', data.get('Note') or data.get('Information'))
        return {}

    payload = {
        'metadata': data.get('metadata'),
        'last_updated': data.get('last_updated'),
        'top_gainers': data.get('top_gainers', []),
        'top_losers': data.get('top_losers', []),
        'most_actively_traded': data.get('most_actively_traded', []),
    }
    await redis.set(cache_key, json.dumps(payload), ex=CacheTTL.MARKET_CONTEXT)
    log_event(
        logger,
        logging.INFO,
        'alpha_vantage_request_completed',
        duration_ms=round((perf_counter() - start) * 1000),
        top_gainers=len(payload['top_gainers']),
        top_losers=len(payload['top_losers']),
        most_active=len(payload['most_actively_traded']),
    )
    return payload
