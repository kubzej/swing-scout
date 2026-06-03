"""
Fundamentals service — P/E, growth, margins, sector info.
Uses yf.Ticker(t).info — cache aggressively (24h), changes quarterly.
Never loop .info for a list — use only for single tickers called as needed.
"""
import yfinance as yf
import json
import logging
from typing import Optional, Dict
from app.core.cache import CacheTTL
from app.services.market.quotes import safe_float

logger = logging.getLogger(__name__)


async def get_fundamentals(redis, ticker: str) -> Dict:
    cache_key = f"ss:fundamentals:{ticker}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = {
        "ticker": ticker,
        "pe": None,
        "forward_pe": None,
        "revenue_growth": None,
        "gross_margin": None,
        "market_cap": None,
        "sector": None,
        "industry": None,
        "country": None,
        "exchange": None,
        "avg_volume": None,
        "quote_type": None,
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info

        result.update({
            "pe": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "gross_margin": safe_float(info.get("grossMargins")),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "exchange": info.get("exchange"),
            "avg_volume": info.get("averageDailyVolume10Day"),
            "quote_type": info.get("quoteType"),
        })
    except Exception as e:
        logger.warning("Fundamentals fetch failed for %s: %s", ticker, e)

    await redis.set(cache_key, json.dumps(result), ex=CacheTTL.FINANCIALS)
    return result


def is_valid_stock(fundamentals: Dict) -> bool:
    """Basic quality filter — real company, not OTC garbage."""
    market_cap = fundamentals.get("market_cap")
    exchange = fundamentals.get("exchange", "") or ""
    quote_type = (fundamentals.get("quote_type", "") or "").upper()
    if not market_cap or market_cap < 100_000_000:  # < $100M
        return False
    if quote_type and quote_type != "EQUITY":
        return False
    if exchange.upper() in ("PNK", "GREY", "OTC", "OTCBB"):
        return False
    return True
