"""
Market context — CNN Fear & Greed + index trend model -> market_regime.
Uses CNN as the only sentiment score source.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.cache import CacheTTL
from app.core.run_logging import log_event
from app.core.supabase import get_supabase
from app.services.market.quotes import get_quotes
from app.services.market.technical import get_technicals

logger = logging.getLogger(__name__)

MARKET_CONTEXT_CACHE_VERSION = "v2"
CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_USER_AGENT = "Mozilla/5.0 (compatible; SwingScout/1.0)"
CNN_CACHE_KEY = f"ss:market_context:{MARKET_CONTEXT_CACHE_VERSION}:cnn_fear_greed"
SHARED_CACHE_KEY = f"ss:market_context:{MARKET_CONTEXT_CACHE_VERSION}:shared"


@dataclass
class MarketContext:
    fng_score: Optional[int]
    fng_label: Optional[str]
    fng_week_ago: Optional[int]
    fng_spike: bool
    spy_trend: Optional[str]
    market_regime: str


def _load_shared_market_context(cached: Optional[str]) -> Optional[MarketContext]:
    if not cached:
        return None
    try:
        data = json.loads(cached)
        return MarketContext(**data)
    except Exception:
        return None


def _normalize_cnn_rating(raw_rating: Optional[str]) -> Optional[str]:
    if not raw_rating:
        return None
    normalized = str(raw_rating).strip().lower().replace("-", " ")
    mapping = {
        "extreme fear": "extreme_fear",
        "fear": "fear",
        "neutral": "neutral",
        "greed": "greed",
        "extreme greed": "extreme_greed",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


async def _fetch_cnn_fear_greed(redis) -> tuple[Optional[int], Optional[str]]:
    cached = await redis.get(CNN_CACHE_KEY)
    if cached:
        try:
            data = json.loads(cached)
            return data.get("score"), data.get("label")
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                CNN_FEAR_GREED_URL,
                headers={"User-Agent": CNN_USER_AGENT},
            )
            response.raise_for_status()
            raw = response.json()

        fear_greed = raw.get("fear_and_greed") or {}
        score = fear_greed.get("score")
        rating = _normalize_cnn_rating(fear_greed.get("rating"))
        if score is None:
            return None, rating

        normalized = {
            "score": int(round(float(score))),
            "label": rating,
        }
        await redis.set(CNN_CACHE_KEY, json.dumps(normalized), ex=CacheTTL.MARKET_CONTEXT)
        return normalized["score"], normalized["label"]
    except Exception as exc:
        logger.warning("CNN Fear & Greed fetch failed: %s", exc)
        return None, None


async def _load_fng_history_baseline(user_id: Optional[str], current_score: Optional[int]) -> tuple[Optional[int], bool]:
    if not user_id:
        return None, False
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
        scores = [r["fng_score"] for r in (response.data or []) if r.get("fng_score") is not None]
        if not scores:
            return None, False
        week_ago = int(sum(scores) / len(scores))
        if current_score is None:
            return week_ago, False
        return week_ago, abs(current_score - week_ago) > 15
    except Exception as exc:
        logger.warning("Sentiment history fetch failed: %s", exc)
        return None, False


def _regime_from_signals(score: Optional[int], spy_trend: str, qqq_trend: str, iwm_trend: str) -> str:
    trend_signals = [spy_trend, qqq_trend, iwm_trend]
    bearish_count = sum(1 for trend in trend_signals if trend in ("bearish", "strong_bearish"))
    bullish_count = sum(1 for trend in trend_signals if trend in ("bullish", "strong_bullish"))
    strong_bearish_count = sum(1 for trend in trend_signals if trend == "strong_bearish")
    strong_bullish_count = sum(1 for trend in trend_signals if trend == "strong_bullish")

    if score is not None:
        if score <= 25:
            return "bear"
        if score >= 75:
            return "bull"
        if score <= 40 and bearish_count >= 2:
            return "bear"
        if score >= 60 and bullish_count >= 2:
            return "bull"

    if strong_bearish_count >= 2 or bearish_count == 3:
        return "bear"
    if strong_bullish_count >= 2 or bullish_count == 3:
        return "bull"
    return "neutral"


async def get_market_context(redis, user_id: str = None) -> MarketContext:
    cached = await redis.get(SHARED_CACHE_KEY)
    cached_ctx = _load_shared_market_context(cached)
    if cached_ctx:
        fng_week_ago, fng_spike = await _load_fng_history_baseline(user_id, cached_ctx.fng_score)
        log_event(
            logger,
            logging.INFO,
            "market_context_cache_hit",
            sentiment_source="cnn",
            fng_score=cached_ctx.fng_score,
            fng_label=cached_ctx.fng_label,
            market_regime=cached_ctx.market_regime,
        )
        return MarketContext(
            fng_score=cached_ctx.fng_score,
            fng_label=cached_ctx.fng_label,
            fng_week_ago=fng_week_ago,
            fng_spike=fng_spike,
            spy_trend=cached_ctx.spy_trend,
            market_regime=cached_ctx.market_regime,
        )

    spy_tech = await get_technicals(redis, "SPY")
    qqq_tech = await get_technicals(redis, "QQQ")
    iwm_tech = await get_technicals(redis, "IWM")
    vix_tech = await get_technicals(redis, "^VIX")
    quotes = await get_quotes(redis, ["SPY", "QQQ", "IWM", "^VIX"])
    spy_quote = quotes.get("SPY", {})
    qqq_quote = quotes.get("QQQ", {})
    iwm_quote = quotes.get("IWM", {})
    vix_quote = quotes.get("^VIX", {})

    fng_score, fng_label = await _fetch_cnn_fear_greed(redis)
    fng_week_ago, fng_spike = await _load_fng_history_baseline(user_id, fng_score)

    spy_trend = spy_tech.get("trend_signal", "mixed")
    qqq_trend = qqq_tech.get("trend_signal", "mixed")
    iwm_trend = iwm_tech.get("trend_signal", "mixed")
    regime = _regime_from_signals(fng_score, spy_trend, qqq_trend, iwm_trend)

    ctx = MarketContext(
        fng_score=fng_score,
        fng_label=fng_label,
        fng_week_ago=fng_week_ago,
        fng_spike=fng_spike,
        spy_trend=spy_trend,
        market_regime=regime,
    )

    log_event(
        logger,
        logging.INFO,
        "market_context_computed",
        sentiment_source="cnn",
        fng_score=fng_score,
        fng_label=fng_label,
        fng_week_ago=fng_week_ago,
        fng_spike=fng_spike,
        spy_trend=spy_trend,
        qqq_trend=qqq_trend,
        iwm_trend=iwm_trend,
        spy_change_pct=spy_quote.get("change_pct"),
        qqq_change_pct=qqq_quote.get("change_pct"),
        iwm_change_pct=iwm_quote.get("change_pct"),
        vix_price=vix_tech.get("price"),
        vix_change_pct=vix_quote.get("change_pct"),
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
    await redis.set(SHARED_CACHE_KEY, json.dumps(ctx_dict), ex=CacheTTL.MARKET_CONTEXT)
    return ctx
