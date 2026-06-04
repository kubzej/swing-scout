"""
Recommendation engine — converts candidates and position flags to structured recommendations.
Applies guards: rejection calibration (soft only), operating mode, rotation logic, cash guard, options.
"""
import logging
from typing import Any, List, Optional
from datetime import datetime, timezone

from app.agent.discovery import Candidate
from app.agent.position_monitor import PositionFlag
from app.services.portfolio_service import PortfolioSnapshot
from app.services.market.market_context import MarketContext
from app.core.run_logging import log_event
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)



def build_recommendations_with_diagnostics(
    candidates: List[Candidate],
    flags: List[PositionFlag],
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    user_id: str,
) -> tuple[List[dict], dict[str, Any]]:
    db = get_supabase()
    recommendations = []

    settings = _load_settings(db, user_id)
    max_positions = settings.get("max_positions", 20)
    cash_reserve_pct = float(settings.get("cash_reserve_pct", 0.07))
    recently_rejected = _load_recently_rejected(db, user_id)

    n_positions = len(portfolio.positions)
    portfolio_full = n_positions >= max_positions

    total_portfolio_value = portfolio.total_value_czk
    reserve_min = total_portfolio_value * cash_reserve_pct
    available_cash = portfolio.cash_czk - reserve_min
    log_event(
        logger,
        logging.INFO,
        'recommendation_cash_context',
        total_portfolio_value=round(total_portfolio_value, 2),
        cash_czk=round(portfolio.cash_czk, 2),
        cash_reserve_pct=cash_reserve_pct,
        reserve_min=round(reserve_min, 2),
        available_cash=round(available_cash, 2),
    )

    diagnostics: dict[str, Any] = {
        "candidates_in": len(candidates),
        "position_flags_in": len(flags),
        "recommendations_out": 0,
        "recently_rejected_skipped": 0,
        "portfolio_full_skipped": 0,
        "insufficient_cash_skipped": 0,
        "rotation_recommendations": 0,
        "buy_recommendations": 0,
        "flag_recommendations": 0,
        "cash_reserve_min": round(reserve_min, 2),
        "available_cash_start": round(available_cash, 2),
        "available_cash_end": round(available_cash, 2),
        "skip_reasons": [],
    }

    def record_skip(reason: str, ticker: str, detail: str | None = None) -> None:
        key = f"{reason}_skipped"
        if key in diagnostics:
            diagnostics[key] += 1
        diagnostics["skip_reasons"].append({
            "ticker": ticker,
            "reason": reason,
            "detail": detail,
        })

    for candidate in candidates:
        ticker = candidate.ticker

        if ticker in recently_rejected:
            logger.info('Skipping %s — recently rejected (soft)', ticker)
            record_skip('recently_rejected', ticker)
            log_event(logger, logging.INFO, 'recommendation_candidate_skipped', ticker=ticker, reason='recently_rejected')
            continue

        if portfolio_full:
            rotation = _find_rotation_candidate(portfolio, flags)
            if not rotation:
                logger.info('Portfolio full, no rotation candidate for %s', ticker)
                record_skip('portfolio_full', ticker)
                log_event(logger, logging.INFO, 'recommendation_candidate_skipped', ticker=ticker, reason='portfolio_full')
                continue
            recommendations.append(_make_rotation_recommendation(candidate, rotation['ticker'], rotation.get('reason')))
            diagnostics['rotation_recommendations'] += 1
            log_event(
                logger,
                logging.INFO,
                'recommendation_rotation_created',
                ticker=ticker,
                exit_ticker=rotation['ticker'],
                exit_reason=rotation.get('reason'),
                confidence=candidate.confidence,
            )
            continue

        if available_cash < candidate.recommended_size_czk * 0.5:
            logger.info('Insufficient cash for %s (available: %.0f CZK)', ticker, available_cash)
            record_skip('insufficient_cash', ticker, f'available_cash={available_cash:.0f}')
            log_event(logger, logging.INFO, 'recommendation_candidate_skipped', ticker=ticker, reason='insufficient_cash', available_cash=round(available_cash, 2))
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
                "invalidation_conditions": candidate.invalidation_conditions,
                "profit_taking_plan": candidate.profit_taking_plan,
                "holding_horizon": candidate.holding_horizon,
                "monitoring_focus": candidate.monitoring_focus,
                "sector": candidate.sector,
                "industry": candidate.industry,
                "exchange": candidate.exchange,
                "currency": candidate.currency,
                "current_price": candidate.current_price,
                "recommended_shares": candidate.recommended_shares,
                "reserve_shares": candidate.reserve_shares,
            },
        }

        watchlist_age = _get_watchlist_age(db, user_id, ticker)
        if watchlist_age and watchlist_age >= 14 and candidate.play_type in ("A", "B"):
            rec["options_details"].update({
                "type": "csp_alternative",
                "note": "Alternativně: cash-secured put — prémie za čekání na vstupní cenu.",
            })

        recommendations.append(rec)
        diagnostics['buy_recommendations'] += 1
        log_event(logger, logging.INFO, 'recommendation_created', ticker=ticker, action='buy', confidence=candidate.confidence, size_czk=candidate.recommended_size_czk)
        available_cash -= candidate.recommended_size_czk

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
            diagnostics["flag_recommendations"] += 1
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
            diagnostics["flag_recommendations"] += 1

        elif flag.flag_type == "thesis_delivered":
            partial_size = round(pos.current_value_czk * 0.5)
            recommendations.append({
                "ticker": flag.ticker,
                "action": "sell",
                "play_type": pos.play_type,
                "confidence": 3,
                "recommended_price": None,
                "recommended_size_czk": partial_size,
                "add_reserve_czk": 0,
                "thesis_text": flag.detail,
                "exit_conditions": "Prodat cca 50 % pozice a zbytek znovu vyhodnotit při dalším denním běhu.",
                "is_options_play": False,
                "options_details": None,
            })
            diagnostics["flag_recommendations"] += 1

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
                "thesis_text": f"Parciální výběr zisku — sentiment spike. Pozice {pos.unrealized_pnl_pct:+.1f}%.",
                "exit_conditions": "Prodat cca 30% pozice.",
                "is_options_play": False,
                "options_details": None,
            })
            diagnostics["flag_recommendations"] += 1

    recommendations.sort(key=lambda r: (r['action'] not in ('exit', 'exit_now'), -r['confidence']))
    diagnostics['recommendations_out'] = len(recommendations)
    log_event(logger, logging.INFO, 'recommendation_engine_completed', diagnostics=diagnostics)
    diagnostics["available_cash_end"] = round(available_cash, 2)
    return recommendations, diagnostics


def build_recommendations(
    candidates: List[Candidate],
    flags: List[PositionFlag],
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    user_id: str,
) -> List[dict]:
    recommendations, _ = build_recommendations_with_diagnostics(
        candidates,
        flags,
        portfolio,
        market_context,
        user_id,
    )
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


def _find_rotation_candidate(portfolio: PortfolioSnapshot, flags: List[PositionFlag]) -> Optional[dict]:
    """Prefer zombie/delivered positions over generic profitable winners for rotation."""
    positions_by_ticker = {pos.ticker: pos for pos in portfolio.positions}

    priority_buckets = [
        ("zombie", 1),
        ("thesis_delivered", 2),
        ("partial_profit", 3),
    ]
    for flag_type, _priority in priority_buckets:
        flagged = []
        for flag in flags:
            if flag.flag_type != flag_type:
                continue
            pos = positions_by_ticker.get(flag.ticker)
            if not pos:
                continue
            flagged.append((pos.unrealized_pnl_pct, flag))
        if flagged:
            flagged.sort(key=lambda item: item[0], reverse=True)
            best_flag = flagged[0][1]
            return {"ticker": best_flag.ticker, "reason": best_flag.detail}

    best_pos = None
    best_pnl = 15.0  # Minimum 15% profit to consider generic rotation
    for pos in portfolio.positions:
        if pos.unrealized_pnl_pct > best_pnl:
            best_pnl = pos.unrealized_pnl_pct
            best_pos = pos
    if best_pos:
        return {
            "ticker": best_pos.ticker,
            "reason": f"Profitová pozice +{best_pos.unrealized_pnl_pct:.1f}% s pravděpodobně nižším upside než nový kandidát.",
        }
    return None


def _make_rotation_recommendation(candidate: Candidate, exit_ticker: str, exit_reason: Optional[str] = None) -> dict:
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
            "note": (
                f"Zvaž prodat {exit_ticker} a otevřít {candidate.ticker}."
                + (f" Důvod rotace: {exit_reason}" if exit_reason else "")
            ),
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
