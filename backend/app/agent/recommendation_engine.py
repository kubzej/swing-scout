"""
Recommendation engine — converts candidates and position flags to structured recommendations.
Applies guards: rejection calibration (soft only), operating mode, rotation logic, cash guard, options.
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone

from app.agent.discovery import Candidate
from app.agent.position_monitor import PositionFlag
from app.services.portfolio_service import PortfolioSnapshot
from app.services.market.market_context import MarketContext
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)


def build_recommendations(
    candidates: List[Candidate],
    flags: List[PositionFlag],
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    user_id: str,
) -> List[dict]:
    db = get_supabase()
    recommendations = []

    # Load settings for max_positions and cash_reserve_pct
    settings = _load_settings(db, user_id)
    max_positions = settings.get("max_positions", 20)
    cash_reserve_pct = float(settings.get("cash_reserve_pct", 0.07))

    # REJECTION CALIBRATION — soft only, no permanent blocks
    recently_rejected = _load_recently_rejected(db, user_id)

    # OPERATING MODE
    n_positions = len(portfolio.positions)
    portfolio_full = n_positions >= max_positions

    # CASH GUARD — reserve based on total portfolio value (grows/shrinks with portfolio)
    total_portfolio_value = portfolio.total_value_czk + portfolio.cash_czk
    reserve_min = total_portfolio_value * cash_reserve_pct
    available_cash = portfolio.cash_czk - reserve_min

    # PROCESS CANDIDATES (new entries)
    for candidate in candidates:
        ticker = candidate.ticker

        # Skip if recently rejected without reason AND conditions haven't materially changed
        if ticker in recently_rejected:
            logger.info("Skipping %s — recently rejected (soft)", ticker)
            continue

        if portfolio_full:
            rotation = _find_rotation_candidate(portfolio)
            if not rotation:
                logger.info("Portfolio full, no rotation candidate for %s", ticker)
                continue
            recommendations.append(_make_rotation_recommendation(candidate, rotation))
            continue

        if available_cash < candidate.recommended_size_czk * 0.5:
            logger.info("Insufficient cash for %s (available: %.0f CZK)", ticker, available_cash)
            continue

        rec = {
            "ticker": ticker,
            "action": "buy",
            "play_type": candidate.play_type,
            "confidence": candidate.confidence,
            "recommended_price": None,
            "recommended_size_czk": candidate.recommended_size_czk,
            "add_reserve_czk": candidate.add_reserve_czk,
            "thesis_text": candidate.thesis,
            "exit_conditions": candidate.exit_conditions,
            "is_options_play": False,
            "options_details": {
                "entry_rationale": candidate.entry_rationale,
                "portfolio_fit_note": candidate.portfolio_fit_note,
                "sector": candidate.sector,
                "industry": candidate.industry,
                "exchange": candidate.exchange,
                "currency": "USD" if candidate.market == "US" else candidate.market,
                "current_price_usd": candidate.current_price_usd,
                "recommended_shares": candidate.recommended_shares,
                "reserve_shares": candidate.reserve_shares,
            },
        }

        # CSP alternative if ticker has been on watchlist >= 14 days
        watchlist_age = _get_watchlist_age(db, user_id, ticker)
        if watchlist_age and watchlist_age >= 14 and candidate.play_type in ("A", "B"):
            rec["options_details"].update({
                "type": "csp_alternative",
                "note": "Alternativně: cash-secured put — prémie za čekání na vstupní cenu.",
            })

        recommendations.append(rec)
        available_cash -= candidate.recommended_size_czk

    # PROCESS POSITION FLAGS
    for flag in flags:
        pos = next((p for p in portfolio.positions if p.ticker == flag.ticker), None)
        if not pos:
            continue

        if flag.flag_type == "add_trigger" and available_cash >= 15000:
            recommendations.append({
                "ticker": flag.ticker,
                "action": "add",
                "play_type": pos.play_type,
                "confidence": 3,
                "recommended_price": None,
                "recommended_size_czk": 17000,
                "add_reserve_czk": 0,
                "thesis_text": f"Dip add — pozice {pos.unrealized_pnl_pct:.1f}% při intaktní tezi.",
                "exit_conditions": "Stejné jako původní thesis.",
                "is_options_play": False,
                "options_details": None,
            })
            available_cash -= 17000

        elif flag.flag_type in ("exit_now", "zombie"):
            recommendations.append({
                "ticker": flag.ticker,
                "action": "exit",
                "play_type": pos.play_type,
                "confidence": 4 if flag.flag_type == "exit_now" else 3,
                "recommended_price": None,
                "recommended_size_czk": 0,
                "add_reserve_czk": 0,
                "thesis_text": flag.detail,
                "exit_conditions": "Prodat celou pozici.",
                "is_options_play": False,
                "options_details": None,
            })

        elif flag.flag_type == "partial_profit":
            partial_size = round(pos.current_value_czk * 0.3)
            recommendations.append({
                "ticker": flag.ticker,
                "action": "sell",
                "play_type": pos.play_type,
                "confidence": 3,
                "recommended_price": None,
                "recommended_size_czk": partial_size,
                "add_reserve_czk": 0,
                "thesis_text": f"Parciální výběr zisku — F&G spike. Pozice {pos.unrealized_pnl_pct:+.1f}%.",
                "exit_conditions": "Prodat cca 30% pozice.",
                "is_options_play": False,
                "options_details": None,
            })

    # Sort: exits first, then by confidence desc
    recommendations.sort(key=lambda r: (r["action"] not in ("exit", "exit_now"), -r["confidence"]))
    return recommendations


def _load_settings(db, user_id: str) -> dict:
    response = db.table("settings").select("*").eq("user_id", user_id).execute()
    return response.data[0] if response.data else {"max_positions": 20, "cash_reserve_pct": 0.07}


def _load_recently_rejected(db, user_id: str) -> set:
    """Load tickers rejected WITHOUT a reason in the last 30 days. Soft skip only."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    response = (
        db.table("recommendations")
        .select("ticker, rejection_reason")
        .eq("user_id", user_id)
        .eq("status", "rejected")
        .is_("rejection_reason", "null")
        .gte("rejected_at", cutoff)
        .execute()
    )
    return {r["ticker"] for r in (response.data or [])}


def _find_rotation_candidate(portfolio: PortfolioSnapshot) -> Optional[str]:
    """Find profitable position where thesis may be delivered (best candidate for rotation)."""
    best = None
    best_pnl = 10.0  # Minimum 10% profit to consider rotation
    for pos in portfolio.positions:
        if pos.unrealized_pnl_pct > best_pnl:
            best_pnl = pos.unrealized_pnl_pct
            best = pos.ticker
    return best


def _make_rotation_recommendation(candidate: Candidate, exit_ticker: str) -> dict:
    return {
        "ticker": candidate.ticker,
        "action": "buy",
        "play_type": candidate.play_type,
        "confidence": candidate.confidence,
        "recommended_price": None,
        "recommended_size_czk": candidate.recommended_size_czk,
        "add_reserve_czk": candidate.add_reserve_czk,
        "thesis_text": f"[Rotace z {exit_ticker}] {candidate.thesis}",
        "exit_conditions": candidate.exit_conditions,
        "is_options_play": False,
        "options_details": {
            "type": "rotation",
            "exit_ticker": exit_ticker,
            "note": f"Zvaž prodat {exit_ticker} (profitová pozice, omezený upside) a otevřít {candidate.ticker}.",
        },
    }


def _get_watchlist_age(db, user_id: str, ticker: str) -> Optional[int]:
    response = (
        db.table("agent_watchlist")
        .select("first_seen_at")
        .eq("user_id", user_id)
        .eq("ticker", ticker)
        .is_("removed_at", "null")
        .execute()
    )
    if not response.data:
        return None
    try:
        first_seen = datetime.fromisoformat(
            response.data[0]["first_seen_at"].replace("Z", "+00:00")
        )
        return (datetime.now(timezone.utc) - first_seen).days
    except Exception:
        return None
