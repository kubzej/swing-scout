"""
Position monitor — thesis validity, zombie detection, add triggers, Type C exit.
Runs as part of daily_run and intraday_run.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.services.portfolio_service import PortfolioSnapshot, PositionSnapshot
from app.services.market.market_context import MarketContext
from app.services.market.technical import get_technicals
from app.search.client import search
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)


@dataclass
class PositionFlag:
    ticker: str
    flag_type: str  # add_trigger | zombie | exit_now | thesis_delivered | partial_profit | news_alert
    detail: str
    urgency: str = "normal"  # normal | high


async def monitor_positions(
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    redis,
    user_id: str,
) -> List[PositionFlag]:
    flags: List[PositionFlag] = []
    db = get_supabase()

    for pos in portfolio.positions:
        ticker = pos.ticker

        # Load thesis
        thesis_response = (
            db.table("theses")
            .select("*")
            .eq("user_id", user_id)
            .eq("position_id", pos.id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        thesis = thesis_response.data[0] if thesis_response.data else None
        thesis_status = thesis.get("status", "intact") if thesis else "intact"
        notes_log = thesis.get("notes_log", []) if thesis else []
        strategy = _get_latest_strategy_snapshot(notes_log)
        technicals = None

        # --- ZOMBIE DETECTION ---
        is_zombie = _check_zombie(thesis_status, notes_log)
        if is_zombie:
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="zombie",
                detail=f"Pozice bez aktivní teze — zvažit exit při příležitosti.",
                urgency="high",
            ))

        if thesis_status == "delivered":
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="thesis_delivered",
                detail=_join_parts(
                    "Teze je označená jako delivered — zvaž realizaci zisku nebo rotaci kapitálu.",
                    _strategy_tail(strategy, "profit_taking_plan", prefix="Původní plán zisků: "),
                ),
            ))

        # --- ADD TRIGGER (Type A/B only) ---
        if pos.play_type != "C" and thesis_status in ("intact",):
            if pos.unrealized_pnl_pct <= -20:
                flags.append(PositionFlag(
                    ticker=ticker,
                    flag_type="add_trigger",
                    detail=f"Pokles {pos.unrealized_pnl_pct:.1f}% — thesis intact, zvažit přikoupení.",
                ))

        # --- TYPE B CATALYST PLAYED OUT / DELIVERED HEURISTIC ---
        if pos.play_type == "B" and thesis_status == "intact" and pos.unrealized_pnl_pct >= 18:
            try:
                technicals = technicals or await get_technicals(redis, ticker)
                rsi14 = technicals.get("rsi14")
                if rsi14 and rsi14 >= 68:
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="thesis_delivered",
                        detail=_join_parts(
                            f"Type B pozice +{pos.unrealized_pnl_pct:.1f}% a RSI {rsi14:.1f} — catalyst může být z velké části odehraný, zvaž staged exit nebo rotaci.",
                            _strategy_tail(strategy, "profit_taking_plan", prefix="Původní plán zisků: "),
                        ),
                    ))
            except Exception:
                pass

        # --- TYPE C EXIT TRIGGER ---
        if pos.play_type == "C" and pos.change_pct is not None:
            if pos.change_pct <= -5:
                flags.append(PositionFlag(
                    ticker=ticker,
                    flag_type="exit_now",
                    detail=_join_parts(
                        f"Type C pozice −{abs(pos.change_pct):.1f}% intraday — exit pravidlo aktivováno.",
                        _strategy_tail(strategy, "invalidation_conditions", prefix="Původní invalidace: "),
                    ),
                    urgency="high",
                ))

        # --- TYPE C PROFIT-TAKING ---
        if pos.play_type == "C" and pos.unrealized_pnl_pct >= 12:
            try:
                technicals = technicals or await get_technicals(redis, ticker)
                rsi14 = technicals.get("rsi14")
                if rsi14 and rsi14 >= 70:
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="partial_profit",
                        detail=_join_parts(
                            f"Type C pozice +{pos.unrealized_pnl_pct:.1f}% a RSI {rsi14:.1f} — zvaž staged výběr zisku.",
                            _strategy_tail(strategy, "profit_taking_plan", prefix="Původní plán zisků: "),
                        ),
                    ))
            except Exception:
                pass

        # --- SENTIMENT SPIKE TACTICAL SIGNAL ---
        if pos.play_type in ("A", "B") and market_context.fng_spike and pos.unrealized_pnl_pct >= 15:
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="partial_profit",
                detail=_join_parts(
                    f"Sentiment spike detekován — pozice +{pos.unrealized_pnl_pct:.1f}%, zvaž parciální výběr zisku.",
                    _strategy_tail(strategy, "profit_taking_plan", prefix="Původní plán zisků: "),
                ),
            ))

        # --- NEWS ALERT (only for flagged positions) ---
        if is_zombie or thesis_status in ("weakening",):
            try:
                news = await search(f"{ticker} stock news latest", max_results=2, days=7)
                if news:
                    snippet = news[0].get("title", "")[:100]
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="news_alert",
                        detail=_join_parts(
                            f"Poslední zprávy: {snippet}",
                            _strategy_tail(strategy, "monitoring_focus", prefix="Co jsi chtěl hlídat: "),
                        ),
                    ))
            except Exception:
                pass

    return flags


def _check_zombie(thesis_status: str, notes_log: list) -> bool:
    if thesis_status == "zombie":
        return True
    if not notes_log:
        return False
    # Check if last note was > 60 days ago
    try:
        last_note = notes_log[-1]
        ts = last_note.get("timestamp")
        if ts:
            last_update = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last_update) > timedelta(days=60):
                return True
        # Check for zombie-like language in last note
        text = last_note.get("text", "").lower()
        zombie_phrases = ["zvažit exit", "zombie", "bez teze", "žádná teze", "waiting for", "no thesis"]
        if any(p in text for p in zombie_phrases):
            return True
    except Exception:
        pass
    return False


def _get_latest_strategy_snapshot(notes_log: list) -> Optional[dict]:
    if not notes_log:
        return None

    for note in reversed(notes_log):
        if note.get("kind") == "strategy_snapshot" and isinstance(note.get("strategy"), dict):
            return note["strategy"]

    return None


def _strategy_tail(strategy: Optional[dict], field: str, *, prefix: str) -> Optional[str]:
    if not strategy:
        return None

    value = strategy.get(field)
    if not value:
        return None

    compact = " ".join(str(value).split())
    if len(compact) > 180:
        compact = compact[:177].rstrip() + "..."

    return f"{prefix}{compact}"


def _join_parts(*parts: Optional[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())
