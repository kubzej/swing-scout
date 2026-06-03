"""
Intraday light run — silent monitoring, only saves recommendation if actionable.
Triggers on: ±5% intraday move, Type C -5% exit, earnings surprise.
"""
import logging
from datetime import datetime, timezone
from time import perf_counter

from app.core.redis import get_redis
from app.core.run_logging import bind_run_context, log_event, reset_run_context
from app.core.supabase import get_supabase
from app.search.client import search
from app.services.market.market_context import get_market_context
from app.services.market.quotes import get_quotes
from app.services.portfolio_service import get_portfolio_snapshot

logger = logging.getLogger(__name__)


async def run_intraday(user_id: str) -> int:
    """Run intraday light monitoring. Returns number of recommendations generated."""
    db = get_supabase()
    redis = get_redis()
    run_key = f"intraday-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    context_token = bind_run_context(run_id=run_key, run_type='intraday', agent_user_id=user_id)
    log_event(logger, logging.INFO, 'intraday_run_started')

    try:
        portfolio = await get_portfolio_snapshot(user_id, redis)
        if not portfolio.positions:
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=0, reason='no_open_positions')
            return 0

        tickers = [p.ticker for p in portfolio.positions]
        stage_started = perf_counter()
        quotes = await get_quotes(redis, tickers)
        market_ctx = await get_market_context(redis, user_id)
        log_event(
            logger,
            logging.INFO,
            'intraday_inputs_loaded',
            duration_ms=round((perf_counter() - stage_started) * 1000),
            positions=len(portfolio.positions),
            quotes=len(quotes),
            market_regime=market_ctx.market_regime,
        )

        recommendations = []

        for pos in portfolio.positions:
            ticker = pos.ticker
            quote = quotes.get(ticker, {})
            change_pct = quote.get('change_pct')

            if change_pct is None:
                log_event(logger, logging.INFO, 'intraday_position_skipped', ticker=ticker, reason='missing_change_pct')
                continue

            if pos.play_type == 'C' and change_pct <= -5:
                recommendations.append({
                    'ticker': ticker,
                    'action': 'exit',
                    'play_type': 'C',
                    'confidence': 4,
                    'recommended_price': quote.get('price') or 0,
                    'recommended_size_czk': 0,
                    'add_reserve_czk': 0,
                    'thesis_text': f'Type C exit pravidlo: −{abs(change_pct):.1f}% intraday bez obratu.',
                    'exit_conditions': 'Exit ihned.',
                    'is_options_play': False,
                    'options_details': None,
                })
                log_event(logger, logging.INFO, 'intraday_recommendation_created', ticker=ticker, action='exit', reason='type_c_rule')
                continue

            if abs(change_pct) >= 5:
                direction = 'klesla' if change_pct < 0 else 'vzrostla'
                news_context = ''
                try:
                    results = await search(f'{ticker} stock news today', max_results=2, days=1)
                    if results:
                        news_context = results[0].get('title', '')
                except Exception as exc:
                    log_event(logger, logging.WARNING, 'intraday_news_lookup_failed', ticker=ticker, error=str(exc), error_type=type(exc).__name__)

                action = 'add' if change_pct <= -5 else 'sell'
                size = 17000 if action == 'add' else round(pos.current_value_czk * 0.3)
                thesis = f'Intraday {direction} {abs(change_pct):.1f}%. {news_context}'

                recommendations.append({
                    'ticker': ticker,
                    'action': action,
                    'play_type': pos.play_type,
                    'confidence': 3,
                    'recommended_price': quote.get('price') or 0,
                    'recommended_size_czk': size,
                    'add_reserve_czk': 0,
                    'thesis_text': thesis,
                    'exit_conditions': 'Viz situace.',
                    'is_options_play': False,
                    'options_details': None,
                })
                log_event(logger, logging.INFO, 'intraday_recommendation_created', ticker=ticker, action=action, change_pct=change_pct)

        if recommendations:
            for rec in recommendations:
                rec['user_id'] = user_id
                rec['run_id'] = None
                rec['status'] = 'pending'
                db.table('recommendations').insert(rec).execute()
            logger.info('Intraday run: %d recommendations generated', len(recommendations))
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=len(recommendations), positions=len(portfolio.positions))
        else:
            logger.info('Intraday run: nothing actionable')
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=0, positions=len(portfolio.positions), reason='nothing_actionable')

        return len(recommendations)
    finally:
        reset_run_context(context_token)
