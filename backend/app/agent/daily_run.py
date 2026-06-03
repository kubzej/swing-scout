"""
Daily run — orchestrates the full daily flow.
Creates a daily_runs record, runs all agent steps, saves results.
"""
import logging
from datetime import datetime, timezone

from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.services.portfolio_service import get_portfolio_snapshot
from app.services.market.market_context import get_market_context
from app.agent.discovery import run_signal_scan, run_deep_filter
from app.agent.position_monitor import monitor_positions
from app.agent.recommendation_engine import build_recommendations
from app.agent.report_generator import generate_report
from app.agent.watchlist_manager import cleanup_stale

logger = logging.getLogger(__name__)


async def run_daily(user_id: str) -> str:
    """Run daily deep flow. Returns run_id."""
    db = get_supabase()
    redis = get_redis()

    # Create run record
    run_record = db.table("daily_runs").insert({
        "user_id": user_id,
        "run_type": "daily",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    run_id = run_record.data[0]["id"]
    logger.info("Daily run started: %s", run_id)

    try:
        # 1. Market context
        logger.info("Fetching market context...")
        market_ctx = await get_market_context(redis, user_id)

        # 2. Portfolio state
        logger.info("Fetching portfolio state...")
        portfolio = await get_portfolio_snapshot(user_id, redis)

        # 3. Re-evaluate pending recommendations
        logger.info("Re-evaluating pending recommendations...")
        await _reevaluate_pending(db, redis, user_id)

        # 4. Position monitor
        logger.info("Running position monitor...")
        position_flags = await monitor_positions(portfolio, market_ctx, redis, user_id)
        logger.info("Position flags: %d", len(position_flags))

        # 5. Discovery
        logger.info("Running discovery Stage 1...")
        signals = await run_signal_scan(redis)

        logger.info("Running discovery Stage 2 (%d signals)...", len(signals))
        candidates = await run_deep_filter(signals, portfolio, market_ctx, redis, user_id)

        discovery_log = {
            "scanned_count": len(signals),
            "signal_tickers": [s.ticker for s in signals[:20]],
            "candidates_found": len(candidates),
        }

        # 6. Recommendation engine
        logger.info("Building recommendations...")
        raw_recs = build_recommendations(candidates, position_flags, portfolio, market_ctx, user_id)

        # 7. Fetch current prices for recommendations
        await _fill_recommended_prices(raw_recs, redis)

        # 8. Save recommendations to DB
        for rec in raw_recs:
            rec["user_id"] = user_id
            rec["run_id"] = run_id
            rec["status"] = "pending"
            db.table("recommendations").insert(rec).execute()

        # 9. Generate report
        logger.info("Generating report...")
        report_content = await generate_report(
            portfolio=portfolio,
            recommendations=raw_recs,
            position_flags=position_flags,
            market_context=market_ctx,
            discovery_log=discovery_log,
            redis=redis,
            user_id=user_id,
        )

        # 10. Portfolio snapshot for history
        portfolio_snapshot = {
            "total_value_czk": portfolio.total_value_czk,
            "total_cost_czk": portfolio.total_cost_czk,
            "total_pnl_czk": portfolio.total_pnl_czk,
            "cash_czk": portfolio.cash_czk,
            "total_return_pct": portfolio.total_return_pct,
            "n_positions": len(portfolio.positions),
        }

        # 11. Cleanup stale watchlist
        await cleanup_stale(user_id)

        # 12. Mark completed
        db.table("daily_runs").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "report_content": report_content,
            "market_regime": market_ctx.market_regime,
            "fng_score": market_ctx.fng_score,
            "fng_week_ago": market_ctx.fng_week_ago,
            "portfolio_snapshot": portfolio_snapshot,
            "discovery_log": discovery_log,
        }).eq("id", run_id).execute()

        logger.info("Daily run completed: %s", run_id)

    except Exception as e:
        logger.error("Daily run failed: %s", e, exc_info=True)
        db.table("daily_runs").update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error_message": str(e),
        }).eq("id", run_id).execute()
        raise

    return run_id


async def _reevaluate_pending(db, redis, user_id: str):
    """Re-evaluate pending recommendations — flag if price changed materially."""
    from app.services.market.quotes import get_quotes

    pending = (
        db.table("recommendations")
        .select("id, ticker, recommended_price, action")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )
    if not pending.data:
        return

    tickers = list({r["ticker"] for r in pending.data})
    quotes = await get_quotes(redis, tickers)

    for rec in pending.data:
        ticker = rec["ticker"]
        rec_price = float(rec.get("recommended_price") or 0)
        current_price = quotes.get(ticker, {}).get("price")

        if not current_price or not rec_price:
            continue

        change = abs(current_price - rec_price) / rec_price * 100
        if change >= 5:
            direction = "vzrostla" if current_price > rec_price else "klesla"
            note = f"Cena {direction} o {change:.1f}% od doporučení (${rec_price:.2f} → ${current_price:.2f})"
            db.table("recommendations").update({
                "status": "updated",
                "price_update_note": note,
            }).eq("id", rec["id"]).execute()


async def _fill_recommended_prices(recommendations: list, redis):
    """Fill in current market prices for recommendations. None if price unavailable."""
    from app.services.market.quotes import get_quotes
    tickers = list({r["ticker"] for r in recommendations})
    quotes = await get_quotes(redis, tickers)
    for rec in recommendations:
        quote = quotes.get(rec["ticker"], {})
        rec["recommended_price"] = quote.get("price")  # None is valid — column is nullable
