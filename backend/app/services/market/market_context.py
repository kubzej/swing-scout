"""
Market context — Fear & Greed index + SPY trend → market_regime.
Used by agent for entry bar calibration and F&G spike detection.
"""
import json
import logging
from typing import Optional
from dataclasses import dataclass
from app.core.cache import CacheTTL
from app.core.supabase import get_supabase
from app.services.market.technical import get_technicals
from app.search.client import search

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    fng_score: Optional[int]       # 0-100
    fng_label: Optional[str]       # extreme_fear / fear / neutral / greed / extreme_greed
    fng_week_ago: Optional[int]    # from DB (last 7 daily runs)
    fng_spike: bool                # |fng - fng_week_ago| > 15
    spy_trend: Optional[str]       # strong_bullish / bullish / mixed / bearish / strong_bearish
    market_regime: str             # bear / neutral / bull


def _parse_fng(text: str) -> Optional[int]:
    import re
    matches = re.findall(r'\b([0-9]{1,3})\b', text)
    for m in matches:
        val = int(m)
        if 0 <= val <= 100:
            return val
    return None


async def get_market_context(redis, user_id: str = None) -> MarketContext:
    cache_key = "ss:market_context"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return MarketContext(**data)

    fng_score = None
    fng_label = None

    # F&G from CNN via Tavily
    try:
        results = await search("CNN Fear Greed index current score today", max_results=3, days=1)
        for r in results:
            text = f"{r.get('title', '')} {r.get('content', '')}"
            score = _parse_fng(text)
            if score is not None:
                fng_score = score
                if score < 25:
                    fng_label = "extreme_fear"
                elif score < 45:
                    fng_label = "fear"
                elif score < 55:
                    fng_label = "neutral"
                elif score < 75:
                    fng_label = "greed"
                else:
                    fng_label = "extreme_greed"
                break
    except Exception as e:
        logger.warning("F&G fetch failed: %s", e)

    # F&G week ago from DB
    fng_week_ago = None
    fng_spike = False
    if user_id:
        try:
            db = get_supabase()
            response = (
                db.table("daily_runs")
                .select("fng_score")
                .eq("user_id", user_id)
                .eq("run_type", "daily")
                .eq("status", "completed")
                .order("started_at", desc=True)
                .limit(7)
                .execute()
            )
            scores = [r["fng_score"] for r in (response.data or []) if r.get("fng_score")]
            if scores:
                fng_week_ago = int(sum(scores) / len(scores))
                if fng_score and abs(fng_score - fng_week_ago) > 15:
                    fng_spike = True
        except Exception as e:
            logger.warning("F&G week ago fetch failed: %s", e)

    # SPY trend
    spy_trend = "mixed"
    try:
        spy_tech = await get_technicals(redis, "SPY")
        spy_trend = spy_tech.get("trend_signal", "mixed")
    except Exception as e:
        logger.warning("SPY technicals failed: %s", e)

    # Market regime
    if spy_trend in ("strong_bearish", "bearish") or (fng_score and fng_score < 25):
        regime = "bear"
    elif spy_trend in ("strong_bullish", "bullish") and (not fng_score or fng_score > 40):
        regime = "bull"
    else:
        regime = "neutral"

    ctx = MarketContext(
        fng_score=fng_score,
        fng_label=fng_label,
        fng_week_ago=fng_week_ago,
        fng_spike=fng_spike,
        spy_trend=spy_trend,
        market_regime=regime,
    )

    ctx_dict = {
        "fng_score": ctx.fng_score,
        "fng_label": ctx.fng_label,
        "fng_week_ago": ctx.fng_week_ago,
        "fng_spike": ctx.fng_spike,
        "spy_trend": ctx.spy_trend,
        "market_regime": ctx.market_regime,
    }
    await redis.set(cache_key, json.dumps(ctx_dict), ex=CacheTTL.MARKET_CONTEXT)
    return ctx
