"""
Daily run — orchestrates the full daily flow.
Creates a daily_runs record, runs all agent steps, saves results.
"""
import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.ai.client import call_llm
from app.agent.discovery import SignalTicker, run_deep_filter_with_diagnostics, run_signal_scan
from app.agent.position_monitor import monitor_positions
from app.agent.recommendation_engine import build_recommendations_with_diagnostics
from app.agent.report_generator import generate_report
from app.agent.watchlist_manager import cleanup_stale, get_active_watchlist
from app.core.redis import get_redis
from app.core.run_logging import bind_run_context, log_event, reset_run_context
from app.core.supabase import get_supabase
from app.search.client import format_results, search
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

PENDING_RECOMMENDATION_REVIEW_PROMPT = """Jsi daily re-check pro čekající swing doporučení.
Vyhodnoť, jestli původní doporučení stále dává smysl.

Vrať POUZE JSON:
{
  "status": "keep|update|reject",
  "thesis_risk": "low|medium|high",
  "summary": "jedna krátká věta česky",
  "price_note": "krátká poznámka k ceně nebo null"
}

Pravidla:
- Pending doporučení není pozice. Cílem je zabránit nákupu staré nebo rozbité teze.
- Reject pokud čerstvý kontext rozbíjí tezi, catalyst selhal, vstup je jen chasing, nebo původní důvod nákupu už neplatí.
- Update pokud teze stále může platit, ale cena/kontext významně mění timing, risk/reward nebo vyžaduje pozornost uživatele.
- Keep pouze pokud původní teze a entry rationale stále drží.
- Cena sama o sobě nestačí. Vždy ji posuzuj proti tezi a čerstvému kontextu."""


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
        signals, watchlist_signal_count = await _merge_watchlist_signals(user_id, signals)
        log_event(logger, logging.INFO, 'stage_completed', stage='discovery_stage_1', duration_ms=round((perf_counter() - stage_started) * 1000), signals=len(signals), watchlist_signals=watchlist_signal_count)

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
    """Re-evaluate pending/updated recommendations against price and thesis context."""
    from app.services.market.quotes import get_quotes

    pending = (
        db.table('recommendations')
        .select('id, ticker, action, play_type, confidence, recommended_price, thesis_text, exit_conditions, options_details, status, created_at, price_update_note')
        .eq('user_id', user_id)
        .in_('status', ['pending', 'updated'])
        .order('created_at', desc=False)
        .limit(30)
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

        if not current_price:
            continue

        change = _price_change_pct(rec_price, current_price)
        action = rec.get('action')
        is_entry = action in ('buy', 'add', 'csp', 'long_call')

        if not is_entry:
            if change is not None and abs(change) >= 5:
                db.table('recommendations').update({
                    'status': 'updated',
                    'price_update_note': _format_price_note(change, rec_price, current_price, symbol),
                }).eq('id', rec['id']).execute()
            continue

        should_review = (
            rec.get('status') == 'updated'
            or change is None
            or abs(change) >= 5
            or _recommendation_age_days(rec) >= 1
        )
        if not should_review:
            continue

        try:
            review = await _review_pending_recommendation(rec, current_price, change)
        except Exception as exc:
            logger.warning("Pending recommendation review failed for %s: %s", ticker, exc)
            if change is not None and abs(change) >= 5:
                db.table('recommendations').update({
                    'status': 'updated',
                    'price_update_note': _format_price_note(change, rec_price, current_price, symbol),
                }).eq('id', rec['id']).execute()
            continue

        review_status = review.get('status')
        summary = review.get('summary') or 'Denní re-check doporučení.'
        price_note = review.get('price_note') or (
            _format_price_note(change, rec_price, current_price, symbol)
            if change is not None and abs(change) >= 5
            else None
        )
        combined_note = _join_parts(price_note, summary)

        if review_status == 'reject':
            db.table('recommendations').update({
                'status': 'rejected',
                'rejection_reason': f"Daily re-check: {summary}",
                'rejected_at': datetime.now(timezone.utc).isoformat(),
                'price_update_note': combined_note,
            }).eq('id', rec['id']).execute()
            log_event(logger, logging.INFO, 'pending_recommendation_rejected', ticker=ticker, action=action, thesis_risk=review.get('thesis_risk'), summary=summary[:160])
            continue

        if review_status == 'update' or price_note:
            db.table('recommendations').update({
                'status': 'updated',
                'price_update_note': combined_note,
            }).eq('id', rec['id']).execute()
            log_event(logger, logging.INFO, 'pending_recommendation_updated', ticker=ticker, action=action, thesis_risk=review.get('thesis_risk'), summary=summary[:160])


async def _review_pending_recommendation(rec: dict, current_price: float, change_pct: float | None) -> dict:
    ticker = rec['ticker']
    options_details = rec.get('options_details') or {}

    try:
        news_results = await search(f"{ticker} stock latest earnings guidance analyst news", max_results=3, days=7)
        news_context = format_results(news_results)
    except Exception:
        news_context = "Zadne vysledky nenalezeny."

    user_prompt = f"""Ticker: {ticker}
Action: {rec.get('action')}
Play type: {rec.get('play_type')}
Confidence: {rec.get('confidence')}
Created at: {rec.get('created_at')}
Current status: {rec.get('status')}
Recommended price: {rec.get('recommended_price')}
Current price: {current_price}
Price change pct from recommendation: {change_pct}

Original thesis:
{rec.get('thesis_text')}

Exit / invalidation:
{rec.get('exit_conditions')}
Stored invalidation: {options_details.get('invalidation_conditions')}
Profit-taking plan: {options_details.get('profit_taking_plan')}
Entry rationale: {options_details.get('entry_rationale')}
Monitoring focus: {options_details.get('monitoring_focus')}

Fresh context:
{news_context[:1200]}"""

    response = await call_llm(
        PENDING_RECOMMENDATION_REVIEW_PROMPT,
        user_prompt,
        max_tokens=260,
        label=f'pending_recommendation_review:{ticker}',
    )
    parsed = _parse_json_object(response)
    if not parsed:
        return {
            "status": "update",
            "thesis_risk": "unknown",
            "summary": "Denní re-check nebylo možné spolehlivě parsovat.",
            "price_note": None,
        }
    return parsed


def _price_change_pct(recommended_price: float, current_price: float) -> float | None:
    if not recommended_price:
        return None
    return (current_price - recommended_price) / recommended_price * 100


def _format_price_note(change_pct: float | None, old_price: float, current_price: float, symbol: str) -> str | None:
    if change_pct is None:
        return None

    direction = 'vzrostla' if change_pct > 0 else 'klesla'
    return (
        f"Cena {direction} o {abs(change_pct):.1f}% od doporučení "
        f"({symbol}{old_price:.2f} → {symbol}{current_price:.2f})"
    )


def _recommendation_age_days(rec: dict) -> int:
    created_at = rec.get('created_at')
    if not created_at:
        return 0
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - created).days)
    except Exception:
        return 0


def _parse_json_object(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _join_parts(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


async def _merge_watchlist_signals(user_id: str, signals: list[SignalTicker]) -> tuple[list[SignalTicker], int]:
    signal_by_ticker = {signal.ticker: signal for signal in signals}
    added = 0

    for item in await get_active_watchlist(user_id):
        ticker = str(item.get("ticker") or "").upper()
        if not ticker or ticker in signal_by_ticker:
            continue

        stage = item.get("stage") or "watching"
        reason = item.get("signal_reason") or "Aktivní watchlist — daily re-check."
        signal_by_ticker[ticker] = SignalTicker(
            ticker=ticker,
            signal_type=f"watchlist_{stage}",
            signal_reason=reason,
            market="EU_HK" if "." in ticker else "US",
            signal_score=2.4 if stage == "candidate" else 1.7,
        )
        added += 1

    merged = list(signal_by_ticker.values())
    merged.sort(key=lambda sig: sig.signal_score, reverse=True)
    return merged, added


async def _fill_recommended_prices(recommendations: list, redis):
    """Fill in current market prices for recommendations. None if price unavailable."""
    from app.services.market.quotes import get_quotes

    tickers = list({r['ticker'] for r in recommendations})
    quotes = await get_quotes(redis, tickers)
    for rec in recommendations:
        quote = quotes.get(rec['ticker'], {})
        rec['recommended_price'] = quote.get('price')  # None is valid — column is nullable
