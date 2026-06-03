"""
Agent watchlist lifecycle — add, promote, remove, cleanup.
Called by discovery pipeline and daily run.
"""
import logging
from datetime import datetime, timezone, timedelta
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)


async def add_or_update_watchlist(user_id: str, ticker: str, stage: str,
                                   signal_reason: str = None, theme: str = None):
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user_id,
        "ticker": ticker.upper(),
        "stage": stage,
        "signal_reason": signal_reason,
        "theme": theme,
        "last_updated_at": now,
        "removed_at": None,
    }
    # Upsert on (user_id, ticker)
    db.table("agent_watchlist").upsert(payload, on_conflict="user_id,ticker").execute()


async def promote_to_candidate(user_id: str, ticker: str):
    db = get_supabase()
    db.table("agent_watchlist").update({
        "stage": "candidate",
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("user_id", user_id).eq("ticker", ticker.upper()).is_("removed_at", "null").execute()


async def remove_from_watchlist(user_id: str, ticker: str):
    db = get_supabase()
    db.table("agent_watchlist").update({
        "removed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("user_id", user_id).eq("ticker", ticker.upper()).execute()


async def cleanup_stale(user_id: str, days: int = 30):
    """Remove watching-stage tickers not updated in N days."""
    db = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    response = (
        db.table("agent_watchlist")
        .select("ticker")
        .eq("user_id", user_id)
        .eq("stage", "watching")
        .is_("removed_at", "null")
        .lt("last_updated_at", cutoff)
        .execute()
    )
    stale = [r["ticker"] for r in (response.data or [])]
    if stale:
        db.table("agent_watchlist").update({
            "removed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).in_("ticker", stale).execute()
        logger.info("Cleaned up %d stale watchlist entries", len(stale))


async def get_active_watchlist(user_id: str) -> list:
    db = get_supabase()
    response = (
        db.table("agent_watchlist")
        .select("*")
        .eq("user_id", user_id)
        .is_("removed_at", "null")
        .order("last_updated_at", desc=True)
        .execute()
    )
    return response.data or []
