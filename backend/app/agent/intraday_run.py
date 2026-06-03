"""
Intraday light run — silent monitoring, only saves recommendation if actionable.
Triggers on: ±5% intraday move, Type C -5% exit, earnings surprise.
"""
import logging
from datetime import datetime, timezone

from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.services.portfolio_service import get_portfolio_snapshot
from app.services.market.quotes import get_quotes
from app.services.market.market_context import get_market_context
from app.search.client import search

logger = logging.getLogger(__name__)


async def run_intraday(user_id: str) -> int:
    """Run intraday light monitoring. Returns number of recommendations generated."""
    db = get_supabase()
    redis = get_redis()

    portfolio = await get_portfolio_snapshot(user_id, redis)
    if not portfolio.positions:
        return 0

    tickers = [p.ticker for p in portfolio.positions]
    quotes = await get_quotes(redis, tickers)
    market_ctx = await get_market_context(redis, user_id)

    recommendations = []

    for pos in portfolio.positions:
        ticker = pos.ticker
        quote = quotes.get(ticker, {})
        change_pct = quote.get("change_pct")

        if change_pct is None:
            continue

        # Type C: -5% exit
        if pos.play_type == "C" and change_pct <= -5:
            recommendations.append({
                "ticker": ticker,
                "action": "exit",
                "play_type": "C",
                "confidence": 4,
                "recommended_price": quote.get("price") or 0,
                "recommended_size_czk": 0,
                "add_reserve_czk": 0,
                "thesis_text": f"Type C exit pravidlo: −{abs(change_pct):.1f}% intraday bez obratu.",
                "exit_conditions": "Exit ihned.",
                "is_options_play": False,
                "options_details": None,
            })
            continue

        # Large intraday move on any position
        if abs(change_pct) >= 5:
            direction = "klesla" if change_pct < 0 else "vzrostla"
            news_context = ""
            try:
                results = await search(f"{ticker} stock news today", max_results=2, days=1)
                if results:
                    news_context = results[0].get("title", "")
            except Exception:
                pass

            # add on dip, partial sell on spike
            action = "add" if change_pct <= -5 else "sell"
            # For partial sell: sell 30% of current value; for add: 17k CZK
            size = 17000 if action == "add" else round(pos.current_value_czk * 0.3)
            thesis = f"Intraday {direction} {abs(change_pct):.1f}%. {news_context}"

            recommendations.append({
                "ticker": ticker,
                "action": action,
                "play_type": pos.play_type,
                "confidence": 3,
                "recommended_price": quote.get("price") or 0,
                "recommended_size_czk": size,
                "add_reserve_czk": 0,
                "thesis_text": thesis,
                "exit_conditions": "Viz situace.",
                "is_options_play": False,
                "options_details": None,
            })

    if recommendations:
        for rec in recommendations:
            rec["user_id"] = user_id
            rec["run_id"] = None
            rec["status"] = "pending"
            db.table("recommendations").insert(rec).execute()
        logger.info("Intraday run: %d recommendations generated", len(recommendations))
    else:
        logger.info("Intraday run: nothing actionable")

    return len(recommendations)
