"""
Market context — internal sentiment score + index trend model -> market_regime.
Used by the agent for entry calibration and risk posture.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.cache import CacheTTL
from app.core.run_logging import log_event
from app.core.supabase import get_supabase
from app.services.market.technical import get_technicals

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    fng_score: Optional[int]
    fng_label: Optional[str]
    fng_week_ago: Optional[int]
    fng_spike: bool
    spy_trend: Optional[str]
    market_regime: str


def _score_trend(signal: str, strong_weight: int, moderate_weight: int) -> int:
    mapping = {
        'strong_bullish': strong_weight,
        'bullish': moderate_weight,
        'mixed': 0,
        'bearish': -moderate_weight,
        'strong_bearish': -strong_weight,
    }
    return mapping.get(signal or 'mixed', 0)


def _score_rsi(value: Optional[float], weight: int) -> int:
    if value is None:
        return 0
    if value <= 35:
        return -weight
    if value >= 65:
        return weight
    if value < 45:
        return -(weight // 2)
    if value > 55:
        return weight // 2
    return 0


def _score_vix(price: Optional[float]) -> int:
    if price is None:
        return 0
    if price >= 30:
        return -12
    if price >= 25:
        return -8
    if price >= 20:
        return -5
    if price <= 14:
        return 6
    if price <= 17:
        return 3
    return 0


def _label_from_score(score: int) -> str:
    if score < 20:
        return 'extreme_fear'
    if score < 40:
        return 'fear'
    if score < 60:
        return 'neutral'
    if score < 85:
        return 'greed'
    return 'extreme_greed'


def _load_shared_market_context(cached: Optional[str]) -> Optional[MarketContext]:
    if not cached:
        return None
    data = json.loads(cached)
    return MarketContext(**data)


async def _load_fng_history_baseline(user_id: Optional[str], current_score: Optional[int]) -> tuple[Optional[int], bool]:
    if not user_id:
        return None, False
    try:
        db = get_supabase()
        response = (
            db.table('daily_runs')
            .select('fng_score')
            .eq('user_id', user_id)
            .eq('run_type', 'daily')
            .eq('status', 'completed')
            .order('started_at', desc=True)
            .limit(7)
            .execute()
        )
        scores = [r['fng_score'] for r in (response.data or []) if r.get('fng_score') is not None]
        if not scores:
            return None, False
        week_ago = int(sum(scores) / len(scores))
        if current_score is None:
            return week_ago, False
        return week_ago, abs(current_score - week_ago) > 15
    except Exception as e:
        logger.warning('F&G week ago fetch failed: %s', e)
        return None, False


def _regime_from_signals(score: Optional[int], spy_trend: str, qqq_trend: str, iwm_trend: str) -> str:
    trend_signals = [spy_trend, qqq_trend, iwm_trend]
    bearish_count = sum(1 for trend in trend_signals if trend in ('bearish', 'strong_bearish'))
    strong_bearish_count = sum(1 for trend in trend_signals if trend == 'strong_bearish')
    bullish_count = sum(1 for trend in trend_signals if trend in ('bullish', 'strong_bullish'))

    if score is not None and score < 35 and (strong_bearish_count >= 1 or bearish_count >= 2):
        return 'bear'
    if score is not None and score < 25:
        return 'bear'
    if score is not None and score > 65 and bullish_count >= 2:
        return 'bull'
    if spy_trend == 'strong_bullish' and qqq_trend in ('bullish', 'strong_bullish'):
        return 'bull'
    return 'neutral'


async def get_market_context(redis, user_id: str = None) -> MarketContext:
    cache_key = 'ss:market_context:shared'
    cached = await redis.get(cache_key)
    cached_ctx = _load_shared_market_context(cached)
    if cached_ctx:
        fng_week_ago, fng_spike = await _load_fng_history_baseline(user_id, cached_ctx.fng_score)
        return MarketContext(
            fng_score=cached_ctx.fng_score,
            fng_label=cached_ctx.fng_label,
            fng_week_ago=fng_week_ago,
            fng_spike=fng_spike,
            spy_trend=cached_ctx.spy_trend,
            market_regime=cached_ctx.market_regime,
        )

    spy_tech = await get_technicals(redis, 'SPY')
    qqq_tech = await get_technicals(redis, 'QQQ')
    iwm_tech = await get_technicals(redis, 'IWM')
    vix_tech = await get_technicals(redis, '^VIX')

    components = {
        'spy_trend': _score_trend(spy_tech.get('trend_signal', 'mixed'), 12, 7),
        'qqq_trend': _score_trend(qqq_tech.get('trend_signal', 'mixed'), 9, 5),
        'iwm_trend': _score_trend(iwm_tech.get('trend_signal', 'mixed'), 7, 4),
        'spy_rsi': _score_rsi(spy_tech.get('rsi14'), 6),
        'qqq_rsi': _score_rsi(qqq_tech.get('rsi14'), 4),
        'iwm_rsi': _score_rsi(iwm_tech.get('rsi14'), 3),
        'vix_level': _score_vix(vix_tech.get('price')),
    }

    raw_score = 50 + sum(components.values())
    fng_score = max(0, min(100, int(round(raw_score))))
    fng_label = _label_from_score(fng_score)

    fng_week_ago, fng_spike = await _load_fng_history_baseline(user_id, fng_score)

    spy_trend = spy_tech.get('trend_signal', 'mixed')
    qqq_trend = qqq_tech.get('trend_signal', 'mixed')
    iwm_trend = iwm_tech.get('trend_signal', 'mixed')
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
        'market_context_computed',
        fng_score=fng_score,
        fng_label=fng_label,
        fng_week_ago=fng_week_ago,
        fng_spike=fng_spike,
        spy_trend=spy_trend,
        qqq_trend=qqq_trend,
        iwm_trend=iwm_trend,
        vix_price=vix_tech.get('price'),
        market_regime=regime,
        components=components,
    )

    ctx_dict = {
        'fng_score': ctx.fng_score,
        'fng_label': ctx.fng_label,
        'fng_week_ago': ctx.fng_week_ago,
        'fng_spike': ctx.fng_spike,
        'spy_trend': ctx.spy_trend,
        'market_regime': ctx.market_regime,
    }
    await redis.set(cache_key, json.dumps(ctx_dict), ex=CacheTTL.MARKET_CONTEXT)
    return ctx
