"""
Daily run — orchestrates the full daily flow.
Creates a daily_runs record, runs all agent steps, saves results.
"""
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.agent.discovery import run_deep_filter_with_diagnostics, run_signal_scan
from app.agent.position_monitor import monitor_positions
from app.agent.recommendation_engine import build_recommendations_with_diagnostics
from app.agent.report_generator import generate_report
from app.agent.watchlist_manager import cleanup_stale
from app.core.redis import get_redis
from app.core.run_logging import bind_run_context, log_event, reset_run_context
from app.core.supabase import get_supabase
from app.services.market.market_context import get_market_context
from app.services.portfolio_service import get_portfolio_snapshot

logger = logging.getLogger(__name__)

CURRENCY_SYMBOL = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "HKD": "HK$",
    "CZK": "Kč",
    "NOK": "kr",
    "DKK": "kr",
    "CHF": "CHF",
    "SEK": "kr",
    "PLN": "zł",
}


class RunIssueCollector(logging.Handler):
    """Collect warning/error records so the UI can surface degraded runs."""

    def __init__(self, max_items: int | None = None):
        super().__init__(level=logging.WARNING)
        self.max_items = max_items
        self.total_count = 0
        self.warning_sources: list[str] = []
        self.warnings: list[dict[str, str]] = []
        self._seen: set[tuple[str, str, str]] = set()

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return

        message = record.getMessage().strip()
        if not message:
            return

        source = record.name.removeprefix('app.')
        issue_key = (record.levelname, source, message)
        if issue_key in self._seen:
            return

        self._seen.add(issue_key)
        self.total_count += 1

        if source not in self.warning_sources:
            self.warning_sources.append(source)

        if self.max_items is None or len(self.warnings) < self.max_items:
            self.warnings.append({
                'level': record.levelname,
                'source': source,
                'message': message,
            })

    def snapshot(self) -> dict[str, Any]:
        return {
            'warnings_count': self.total_count,
            'degraded_mode': self.total_count > 0,
            'warning_sources': self.warning_sources,
            'warnings': self.warnings,
        }


def _build_discovery_log(
    signals: list,
    candidates: list,
    collector: RunIssueCollector,
    *,
    stage2_diagnostics: dict[str, Any] | None = None,
    recommendation_diagnostics: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    failed_step: str | None = None,
) -> dict[str, Any]:
    discovery_log = {
        'scanned_count': len(signals),
        'signal_tickers': [signal.ticker for signal in signals[:20]],
        'candidates_found': len(candidates),
    }
    discovery_log.update(collector.snapshot())

    if stage2_diagnostics is not None:
        discovery_log["stage2_diagnostics"] = stage2_diagnostics
    if recommendation_diagnostics is not None:
        discovery_log["recommendation_diagnostics"] = recommendation_diagnostics

    if failed_step:
        discovery_log['failed_step'] = failed_step
    if failure_reason:
        discovery_log['failure_reason'] = failure_reason

    return discovery_log


async def run_daily(user_id: str) -> str:
    """Run daily deep flow. Returns run_id."""
    db = get_supabase()
    redis = get_redis()
    root_logger = logging.getLogger()
    issue_collector = RunIssueCollector()
    root_logger.addHandler(issue_collector)

    # Create run record
    run_record = db.table('daily_runs').insert({
        'user_id': user_id,
        'run_type': 'daily',
        'status': 'running',
        'started_at': datetime.now(timezone.utc).isoformat(),
    }).execute()
    run_id = run_record.data[0]['id']
    context_token = bind_run_context(run_id=run_id, run_type='daily', agent_user_id=user_id)
    logger.info('Daily run started: %s', run_id)
    log_event(logger, logging.INFO, 'daily_run_started')

    market_ctx = None
    portfolio = None
    signals = []
    candidates = []
    stage2_diagnostics: dict[str, Any] = {}
    recommendation_diagnostics: dict[str, Any] = {}
    step = 'market context'

    try:
        # 1. Market context
        logger.info('Fetching market context...')
        stage_started = perf_counter()
        market_ctx = await get_market_context(redis, user_id)
        log_event(logger, logging.INFO, 'stage_completed', stage='market_context', duration_ms=round((perf_counter() - stage_started) * 1000), market_regime=market_ctx.market_regime, fng_score=market_ctx.fng_score)

        # 2. Portfolio state
        step = 'portfolio state'
        logger.info('Fetching portfolio state...')
        stage_started = perf_counter()
        portfolio = await get_portfolio_snapshot(user_id, redis)
        log_event(logger, logging.INFO, 'stage_completed', stage='portfolio_state', duration_ms=round((perf_counter() - stage_started) * 1000), open_positions=len(portfolio.positions), cash_czk=portfolio.cash_czk)

        # 3. Re-evaluate pending recommendations
        step = 'pending recommendation re-evaluation'
        logger.info('Re-evaluating pending recommendations...')
        stage_started = perf_counter()
        await _reevaluate_pending(db, redis, user_id)
        log_event(logger, logging.INFO, 'stage_completed', stage='pending_recommendation_re_evaluation', duration_ms=round((perf_counter() - stage_started) * 1000))

        # 4. Position monitor
        step = 'position monitor'
        logger.info('Running position monitor...')
        stage_started = perf_counter()
        position_flags = await monitor_positions(portfolio, market_ctx, redis, user_id)
        logger.info('Position flags: %d', len(position_flags))
        log_event(logger, logging.INFO, 'stage_completed', stage='position_monitor', duration_ms=round((perf_counter() - stage_started) * 1000), position_flags=len(position_flags))

        # 5. Discovery
        step = 'discovery stage 1'
        logger.info('Running discovery Stage 1...')
        stage_started = perf_counter()
        signals = await run_signal_scan(redis)
        log_event(logger, logging.INFO, 'stage_completed', stage='discovery_stage_1', duration_ms=round((perf_counter() - stage_started) * 1000), signals=len(signals))

        step = 'discovery stage 2'
        logger.info('Running discovery Stage 2 (%d signals)...', len(signals))
        stage_started = perf_counter()
        candidates, stage2_diagnostics = await run_deep_filter_with_diagnostics(signals, portfolio, market_ctx, redis, user_id)
        log_event(logger, logging.INFO, 'stage_completed', stage='discovery_stage_2', duration_ms=round((perf_counter() - stage_started) * 1000), candidates=len(candidates), diagnostics=stage2_diagnostics)

        # 6. Recommendation engine
        step = 'recommendation engine'
        logger.info('Building recommendations...')
        stage_started = perf_counter()
        raw_recs, recommendation_diagnostics = build_recommendations_with_diagnostics(candidates, position_flags, portfolio, market_ctx, user_id)
        log_event(logger, logging.INFO, 'stage_completed', stage='recommendation_engine', duration_ms=round((perf_counter() - stage_started) * 1000), recommendations=len(raw_recs), diagnostics=recommendation_diagnostics)

        # 7. Fetch current prices for recommendations
        step = 'price enrichment'
        stage_started = perf_counter()
        await _fill_recommended_prices(raw_recs, redis)
        log_event(logger, logging.INFO, 'stage_completed', stage='price_enrichment', duration_ms=round((perf_counter() - stage_started) * 1000), recommendations=len(raw_recs))

        # 8. Save recommendations to DB
        step = 'recommendation persistence'
        stage_started = perf_counter()
        for rec in raw_recs:
            rec['user_id'] = user_id
            rec['run_id'] = run_id
            rec['status'] = 'pending'
            db.table('recommendations').insert(rec).execute()
        log_event(logger, logging.INFO, 'stage_completed', stage='recommendation_persistence', duration_ms=round((perf_counter() - stage_started) * 1000), recommendations=len(raw_recs))

        # 9. Generate report
        step = 'report generation'
        logger.info('Generating report...')
        stage_started = perf_counter()
        discovery_log = _build_discovery_log(signals, candidates, issue_collector, stage2_diagnostics=stage2_diagnostics, recommendation_diagnostics=recommendation_diagnostics)
        report_content = await generate_report(
            portfolio=portfolio,
            recommendations=raw_recs,
            position_flags=position_flags,
            market_context=market_ctx,
            discovery_log=discovery_log,
            redis=redis,
            user_id=user_id,
        )

        log_event(logger, logging.INFO, 'stage_completed', stage='report_generation', duration_ms=round((perf_counter() - stage_started) * 1000), report_chars=len(report_content or ''))

        # 10. Portfolio snapshot for history
        step = 'portfolio snapshot'
        portfolio_snapshot = {
            'total_value_czk': portfolio.total_value_czk,
            'total_cost_czk': portfolio.total_cost_czk,
            'total_pnl_czk': portfolio.total_pnl_czk,
            'cash_czk': portfolio.cash_czk,
            'total_return_pct': portfolio.total_return_pct,
            'n_positions': len(portfolio.positions),
        }

        # 11. Cleanup stale watchlist
        step = 'watchlist cleanup'
        stage_started = perf_counter()
        await cleanup_stale(user_id)
        log_event(logger, logging.INFO, 'stage_completed', stage='watchlist_cleanup', duration_ms=round((perf_counter() - stage_started) * 1000))

        # 12. Mark completed
        step = 'completion'
        discovery_log = _build_discovery_log(signals, candidates, issue_collector, stage2_diagnostics=stage2_diagnostics, recommendation_diagnostics=recommendation_diagnostics)
        db.table('daily_runs').update({
            'status': 'completed',
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'report_content': report_content,
            'market_regime': market_ctx.market_regime,
            'fng_score': market_ctx.fng_score,
            'fng_week_ago': market_ctx.fng_week_ago,
            'portfolio_snapshot': portfolio_snapshot,
            'discovery_log': discovery_log,
        }).eq('id', run_id).execute()

        logger.info('Daily run completed: %s', run_id)
        log_event(logger, logging.INFO, 'daily_run_completed', warnings=issue_collector.total_count, signals=len(signals), candidates=len(candidates), recommendations=len(raw_recs))

    except Exception as e:
        discovery_log = _build_discovery_log(
            signals,
            candidates,
            issue_collector,
            stage2_diagnostics=stage2_diagnostics,
            recommendation_diagnostics=recommendation_diagnostics,
            failure_reason=str(e),
            failed_step=step,
        )
        log_event(logger, logging.ERROR, 'daily_run_failed', stage=step, error=str(e), error_type=type(e).__name__)
        logger.error('Daily run failed during %s: %s', step, e, exc_info=True)
        db.table('daily_runs').update({
            'status': 'failed',
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'error_message': str(e),
            'discovery_log': discovery_log,
        }).eq('id', run_id).execute()
        raise
    finally:
        root_logger.removeHandler(issue_collector)
        reset_run_context(context_token)

    return run_id


async def _reevaluate_pending(db, redis, user_id: str):
    """Re-evaluate pending recommendations — flag if price changed materially."""
    from app.services.market.quotes import get_quotes

    pending = (
        db.table('recommendations')
        .select('id, ticker, recommended_price, action, options_details')
        .eq('user_id', user_id)
        .eq('status', 'pending')
        .execute()
    )
    if not pending.data:
        return

    tickers = list({r['ticker'] for r in pending.data})
    quotes = await get_quotes(redis, tickers)

    for rec in pending.data:
        ticker = rec['ticker']
        rec_price = float(rec.get('recommended_price') or 0)
        current_price = quotes.get(ticker, {}).get('price')
        options_details = rec.get('options_details') or {}
        currency = str(options_details.get('currency') or 'USD').upper()
        symbol = CURRENCY_SYMBOL.get(currency, f"{currency} ")

        if not current_price or not rec_price:
            continue

        change = abs(current_price - rec_price) / rec_price * 100
        if change >= 5:
            direction = 'vzrostla' if current_price > rec_price else 'klesla'
            note = (
                f"Cena {direction} o {change:.1f}% od doporučení "
                f"({symbol}{rec_price:.2f} → {symbol}{current_price:.2f})"
            )
            db.table('recommendations').update({
                'status': 'updated',
                'price_update_note': note,
            }).eq('id', rec['id']).execute()


async def _fill_recommended_prices(recommendations: list, redis):
    """Fill in current market prices for recommendations. None if price unavailable."""
    from app.services.market.quotes import get_quotes

    tickers = list({r['ticker'] for r in recommendations})
    quotes = await get_quotes(redis, tickers)
    for rec in recommendations:
        quote = quotes.get(rec['ticker'], {})
        rec['recommended_price'] = quote.get('price')  # None is valid — column is nullable
