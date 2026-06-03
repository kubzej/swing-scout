"""
Earnings calendar — next earnings date per ticker.
Cache 24h — changes infrequently.
"""
import yfinance as yf
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from app.core.cache import CacheTTL

logger = logging.getLogger(__name__)


async def get_earnings_date(redis, ticker: str) -> Optional[date]:
    cache_key = f"ss:earnings:{ticker}"
    cached = await redis.get(cache_key)
    if cached:
        val = json.loads(cached)
        return date.fromisoformat(val) if val else None

    earnings_date = None
    try:
        t = yf.Ticker(ticker)
        info = t.info
        ts = info.get("earningsTimestamp")
        if ts:
            earnings_date = datetime.fromtimestamp(ts).date()
    except Exception as e:
        logger.warning("Earnings date fetch failed for %s: %s", ticker, e)

    await redis.set(
        cache_key,
        json.dumps(earnings_date.isoformat() if earnings_date else None),
        ex=CacheTTL.EARNINGS,
    )
    return earnings_date


async def get_upcoming_earnings(redis, tickers: List[str], days: int = 7) -> Dict[str, date]:
    """Returns tickers with earnings within the next N days."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    result: Dict[str, date] = {}
    for ticker in tickers:
        d = await get_earnings_date(redis, ticker)
        if d and today <= d <= cutoff:
            result[ticker] = d
    return result
