"""
Intraday light run — monitor open positions and active watchlist names.

Price movement is the trigger. Fresh search/LLM context explains why the move
may have happened and whether it looks thesis-relevant.
"""
import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter

from app.ai.client import call_llm
from app.agent.watchlist_manager import add_or_update_watchlist, get_active_watchlist
from app.core.redis import get_redis
from app.core.run_logging import bind_run_context, log_event, reset_run_context
from app.core.supabase import get_supabase
from app.search.client import format_results, search
from app.services.market.market_context import get_market_context
from app.services.market.quotes import get_intraday_quotes
from app.services.portfolio_service import get_portfolio_snapshot

logger = logging.getLogger(__name__)

MOVE_CONTEXT_PROMPT = """Jsi intraday risk analytik pro swing portfolio.
Price move je už potvrzený z čerstvých intraday dat. Tvůj úkol je pouze vysvětlit pravděpodobný důvod a odhadnout riziko pro tezi.

Vrať POUZE JSON:
{
  "cause_category": "positive_catalyst|earnings_or_guidance|analyst_or_sector_move|routine_volatility|possible_thesis_break|unknown",
  "thesis_risk": "low|medium|high|unknown",
  "summary": "jedna krátká věta česky",
  "action_bias": "add_ok|take_profit_ok|exit_or_avoid|watch_only"
}

Pravidla:
- Nepředstírej jistotu, pokud články neříkají jasný důvod.
- News není trigger. Trigger je cena; news jen vysvětluje, zda move vypadá fundamentálně důležitě.
- Pokud je přiložená původní teze pozice, posuzuj pohyb vůči ní: proč jsme koupili, kdy je teze špatně, kdy brát zisky.
- U propadu po špatném guidance/earnings/účetním/fundamentálním problému dej thesis_risk high.
- U běžné volatility, sektorového pohybu nebo absence jasného důvodu dej thesis_risk low/unknown a action_bias watch_only nebo add_ok podle kontextu."""


async def run_intraday(user_id: str) -> int:
    """Run intraday light monitoring. Returns number of recommendations generated."""
    db = get_supabase()
    redis = get_redis()
    run_key = f"intraday-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    context_token = bind_run_context(run_id=run_key, run_type='intraday', agent_user_id=user_id)
    log_event(logger, logging.INFO, 'intraday_run_started')

    try:
        portfolio = await get_portfolio_snapshot(user_id, redis)
        portfolio_tickers = [p.ticker for p in portfolio.positions]
        held = set(portfolio_tickers)

        watchlist = await get_active_watchlist(user_id)
        watchlist_by_ticker = {
            item["ticker"].upper(): item
            for item in watchlist
            if item.get("ticker") and item["ticker"].upper() not in held
        }

        tickers = sorted(held | set(watchlist_by_ticker.keys()))
        if not tickers:
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=0, reason='no_positions_or_watchlist')
            return 0

        stage_started = perf_counter()
        quotes = await get_intraday_quotes(redis, tickers)
        market_ctx = await get_market_context(redis, user_id)
        log_event(
            logger,
            logging.INFO,
            'intraday_inputs_loaded',
            duration_ms=round((perf_counter() - stage_started) * 1000),
            positions=len(portfolio.positions),
            watchlist=len(watchlist_by_ticker),
            quotes=len(quotes),
            market_regime=market_ctx.market_regime,
        )

        positions_by_ticker = {p.ticker: p for p in portfolio.positions}
        recommendations = []

        for ticker in tickers:
            quote = quotes.get(ticker, {})
            change_pct = quote.get('intraday_change_pct')

            if change_pct is None:
                log_event(logger, logging.INFO, 'intraday_item_skipped', ticker=ticker, reason='missing_intraday_change_pct')
                continue
            if abs(change_pct) < 5:
                continue

            direction = 'klesla' if change_pct < 0 else 'vzrostla'
            pos = positions_by_ticker.get(ticker)

            if pos:
                thesis_context = _load_position_thesis(db, user_id, pos.id)
                move_context = await _assess_intraday_move(ticker, direction, change_pct, quote, thesis_context=thesis_context)
                rec = _build_position_recommendation(
                    db=db,
                    user_id=user_id,
                    pos=pos,
                    quote=quote,
                    change_pct=change_pct,
                    direction=direction,
                    move_context=move_context,
                    thesis_context=thesis_context,
                )
                if rec:
                    recommendations.append(rec)
                    log_event(
                        logger,
                        logging.INFO,
                        'intraday_recommendation_created',
                        ticker=ticker,
                        action=rec['action'],
                        change_pct=change_pct,
                        cause_category=move_context.get('cause_category'),
                        thesis_risk=move_context.get('thesis_risk'),
                    )
                else:
                    log_event(
                        logger,
                        logging.INFO,
                        'intraday_item_skipped',
                        ticker=ticker,
                        reason='move_context_not_actionable',
                        change_pct=change_pct,
                        cause_category=move_context.get('cause_category'),
                        thesis_risk=move_context.get('thesis_risk'),
                    )
                continue

            watch_item = watchlist_by_ticker.get(ticker)
            if not watch_item:
                continue

            move_context = await _assess_intraday_move(ticker, direction, change_pct, quote)
            await add_or_update_watchlist(
                user_id=user_id,
                ticker=ticker,
                stage=watch_item.get("stage", "watching"),
                signal_reason=_intraday_watchlist_reason(ticker, direction, change_pct, move_context),
                theme=watch_item.get("theme"),
            )
            rec = _build_watchlist_recommendation(
                db=db,
                user_id=user_id,
                watch_item=watch_item,
                quote=quote,
                change_pct=change_pct,
                direction=direction,
                move_context=move_context,
            )
            if rec:
                recommendations.append(rec)
                log_event(
                    logger,
                    logging.INFO,
                    'intraday_recommendation_created',
                    ticker=ticker,
                    action=rec['action'],
                    change_pct=change_pct,
                    source='watchlist',
                    cause_category=move_context.get('cause_category'),
                )
            else:
                log_event(
                    logger,
                    logging.INFO,
                    'intraday_watchlist_updated',
                    ticker=ticker,
                    change_pct=change_pct,
                    cause_category=move_context.get('cause_category'),
                    thesis_risk=move_context.get('thesis_risk'),
                )

        if recommendations:
            for rec in recommendations:
                rec['user_id'] = user_id
                rec['run_id'] = None
                rec['status'] = 'pending'
                db.table('recommendations').insert(rec).execute()
            logger.info('Intraday run: %d recommendations generated', len(recommendations))
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=len(recommendations), positions=len(portfolio.positions), watchlist=len(watchlist_by_ticker))
        else:
            logger.info('Intraday run: nothing actionable')
            log_event(logger, logging.INFO, 'intraday_run_completed', recommendations=0, positions=len(portfolio.positions), watchlist=len(watchlist_by_ticker), reason='nothing_actionable')

        return len(recommendations)
    finally:
        reset_run_context(context_token)


async def _assess_intraday_move(ticker: str, direction: str, change_pct: float, quote: dict, thesis_context: dict | None = None) -> dict:
    try:
        results = await search(f"{ticker} stock why moved today earnings guidance analyst news", max_results=3, days=2)
        news_context = format_results(results)
    except Exception as exc:
        log_event(logger, logging.WARNING, 'intraday_move_context_search_failed', ticker=ticker, error=str(exc), error_type=type(exc).__name__)
        news_context = "Zadne vysledky nenalezeny."

    user_prompt = f"""Ticker: {ticker}
Intraday move: {direction} {abs(change_pct):.1f}%
Intraday open: {quote.get('intraday_open')}
Current price: {quote.get('price')}

Původní teze / plán pozice:
{_format_thesis_context(thesis_context) if thesis_context else 'Není k dispozici — jde o watchlist nebo pozici bez uložené teze.'}

Fresh search context:
{news_context[:1200]}"""

    try:
        response = await call_llm(MOVE_CONTEXT_PROMPT, user_prompt, max_tokens=260, label=f'intraday_move_context:{ticker}')
        parsed = _parse_json_object(response)
        if parsed:
            parsed["raw_news_context"] = news_context[:500]
            return parsed
    except Exception as exc:
        log_event(logger, logging.WARNING, 'intraday_move_context_llm_failed', ticker=ticker, error=str(exc), error_type=type(exc).__name__)

    return {
        "cause_category": "unknown",
        "thesis_risk": "unknown",
        "summary": "Nenašel jsem spolehlivé vysvětlení aktuálního pohybu.",
        "action_bias": "watch_only",
        "raw_news_context": news_context[:500],
    }


def _build_position_recommendation(*, db, user_id: str, pos, quote: dict, change_pct: float, direction: str, move_context: dict, thesis_context: dict | None) -> dict | None:
    thesis_risk = move_context.get("thesis_risk", "unknown")
    action_bias = move_context.get("action_bias", "watch_only")
    cause_category = move_context.get("cause_category", "unknown")

    if change_pct <= -5:
        if pos.play_type == 'C' or thesis_risk == 'high' or action_bias == 'exit_or_avoid':
            action = 'exit'
            confidence = 4 if pos.play_type == 'C' or thesis_risk == 'high' else 3
            size = 0
            exit_conditions = 'Prodat celou pozici.'
            prefix = 'Intraday risk trigger'
        elif pos.play_type in ('A', 'B') and thesis_risk == 'low' and action_bias == 'add_ok':
            action = 'add'
            confidence = 3
            size = 17000
            exit_conditions = 'Stejné jako původní thesis; znovu ověřit při dalším denním běhu.'
            prefix = 'Intraday add trigger'
        else:
            return None
    elif change_pct >= 5:
        profit_plan = ((thesis_context or {}).get("strategy") or {}).get("profit_taking_plan")
        if action_bias != 'take_profit_ok' or not profit_plan or change_pct < 10:
            return None
        action = 'sell'
        confidence = 3
        size = round(pos.current_value_czk * 0.3)
        exit_conditions = f'Prodat cca 30 % jen pokud to sedí s původním plánem zisků: {profit_plan}'
        prefix = 'Intraday profit-taking trigger'
    else:
        return None

    if _has_active_recommendation(db, user_id, pos.ticker, action):
        log_event(logger, logging.INFO, 'intraday_item_skipped', ticker=pos.ticker, reason='active_recommendation_exists', action=action)
        return None

    return {
        'ticker': pos.ticker,
        'action': action,
        'play_type': pos.play_type,
        'confidence': confidence,
        'recommended_price': quote.get('price') or 0,
        'recommended_size_czk': size,
        'add_reserve_czk': 0,
        'thesis_text': _intraday_thesis_text(
            ticker=pos.ticker,
            direction=direction,
            change_pct=change_pct,
            quote=quote,
            prefix=prefix,
            move_context=move_context,
        ),
        'exit_conditions': exit_conditions,
        'is_options_play': False,
        'options_details': _intraday_options_details(quote, change_pct, move_context, cause_category, thesis_context),
    }


def _build_watchlist_recommendation(*, db, user_id: str, watch_item: dict, quote: dict, change_pct: float, direction: str, move_context: dict) -> dict | None:
    ticker = watch_item["ticker"].upper()
    cause_category = move_context.get("cause_category", "unknown")
    thesis_risk = move_context.get("thesis_risk", "unknown")
    action_bias = move_context.get("action_bias", "watch_only")

    if change_pct < 5:
        return None
    if thesis_risk == "high" or action_bias == "exit_or_avoid":
        return None
    if cause_category not in ("positive_catalyst", "earnings_or_guidance", "analyst_or_sector_move"):
        return None
    if _has_active_recommendation(db, user_id, ticker, 'buy'):
        log_event(logger, logging.INFO, 'intraday_watchlist_skipped', ticker=ticker, reason='active_buy_recommendation_exists')
        return None

    return {
        'ticker': ticker,
        'action': 'buy',
        'play_type': 'C' if cause_category in ("positive_catalyst", "analyst_or_sector_move") else 'B',
        'confidence': 2,
        'recommended_price': quote.get('price') or 0,
        'recommended_size_czk': 20000,
        'add_reserve_czk': 0,
        'thesis_text': _intraday_thesis_text(
            ticker=ticker,
            direction=direction,
            change_pct=change_pct,
            quote=quote,
            prefix='Watchlist intraday trigger',
            move_context=move_context,
        ),
        'exit_conditions': 'Pouze malý starter; odmítnout pokud se catalyst nepotvrdí nebo momentum do close vyprchá.',
        'is_options_play': False,
        'options_details': _intraday_options_details(quote, change_pct, move_context, cause_category),
    }


def _has_active_recommendation(db, user_id: str, ticker: str, action: str) -> bool:
    response = (
        db.table('recommendations')
        .select('id')
        .eq('user_id', user_id)
        .eq('ticker', ticker)
        .eq('action', action)
        .in_('status', ['pending', 'updated'])
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _load_position_thesis(db, user_id: str, position_id: str) -> dict | None:
    response = (
        db.table("theses")
        .select("*")
        .eq("user_id", user_id)
        .eq("position_id", position_id)
        .execute()
    )
    if not response.data:
        return None

    thesis = response.data[0]
    return {
        "status": thesis.get("status"),
        "entry_thesis": thesis.get("entry_thesis"),
        "entry_rationale": thesis.get("entry_rationale"),
        "invalidation_conditions": thesis.get("invalidation_conditions"),
        "profit_taking_plan": thesis.get("profit_taking_plan"),
        "monitoring_focus": thesis.get("monitoring_focus"),
        "holding_horizon": thesis.get("holding_horizon"),
        "add_plan": thesis.get("add_plan"),
        "exit_plan": thesis.get("exit_plan"),
        "play_type": thesis.get("play_type"),
    }


def _format_thesis_context(thesis_context: dict | None) -> str:
    if not thesis_context:
        return "Není k dispozici."

    parts = [
        f"Status: {thesis_context.get('status')}",
        f"Entry thesis: {thesis_context.get('entry_thesis')}",
        f"Entry rationale: {thesis_context.get('entry_rationale')}",
        f"Invalidation conditions: {thesis_context.get('invalidation_conditions')}",
        f"Profit-taking plan: {thesis_context.get('profit_taking_plan')}",
        f"Horizon: {thesis_context.get('holding_horizon')}",
        f"Monitoring focus: {thesis_context.get('monitoring_focus')}",
    ]
    return "\n".join(part for part in parts if part and not part.endswith(": None"))


def _intraday_thesis_text(*, ticker: str, direction: str, change_pct: float, quote: dict, prefix: str, move_context: dict) -> str:
    open_price = quote.get('intraday_open')
    current_price = quote.get('price')
    summary = move_context.get("summary") or "důvod pohybu není jasný"
    price_part = f"({open_price:.2f} → {current_price:.2f})" if open_price and current_price else ""
    return f'{prefix}: {ticker} {direction} {abs(change_pct):.1f}% od dnešního intraday open {price_part}. Kontext: {summary}'


def _intraday_options_details(quote: dict, change_pct: float, move_context: dict, cause_category: str, thesis_context: dict | None = None) -> dict:
    details = {
        "source": "intraday_price_move",
        "intraday_open": quote.get("intraday_open"),
        "intraday_change_pct": change_pct,
        "move_cause_category": cause_category,
        "move_thesis_risk": move_context.get("thesis_risk"),
        "move_action_bias": move_context.get("action_bias"),
        "move_summary": move_context.get("summary"),
        "raw_news_context": move_context.get("raw_news_context"),
    }
    if thesis_context:
        details["thesis_status"] = thesis_context.get("status")
        details["thesis_profit_taking_plan"] = thesis_context.get("profit_taking_plan")
        details["thesis_invalidation_conditions"] = thesis_context.get("invalidation_conditions")
    return details


def _intraday_watchlist_reason(ticker: str, direction: str, change_pct: float, move_context: dict) -> str:
    summary = move_context.get("summary") or "bez jasného vysvětlení"
    return f"Intraday {ticker} {direction} {abs(change_pct):.1f}% — {summary}"[:220]


def _parse_json_object(text: str) -> dict | None:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    try:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
    return None
