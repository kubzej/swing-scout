"""
Discovery pipeline — two-stage funnel for finding new investment candidates.

Stage 1: Multi-source signal scan — no hardcoded ticker lists.
  - Alpha Vantage supplies daily movers/actives as one signal source
  - Search providers always add earnings / analyst / momentum / regional signals
  - yfinance validates extracted tickers before Stage 2

Stage 2: Deep filter — fundamentals + technicals + thesis generation via Claude.
"""
import asyncio
import json
import logging
import re
from typing import Any, List, Optional
from dataclasses import dataclass
from datetime import date

from app.core.config import get_settings
from app.search.client import search, format_results
from app.services.market.financials import get_fundamentals, is_valid_stock
from app.services.market.alpha_vantage import get_top_movers
from app.services.market.technical import get_technicals
from app.services.market.earnings import get_upcoming_earnings
from app.services.market.quotes import get_fx_rate, get_fx_rates
from app.services.market.market_context import MarketContext
from app.services.portfolio_service import PortfolioSnapshot
from app.ai.client import call_llm
from app.core.run_logging import log_event
from app.agent.watchlist_manager import add_or_update_watchlist

logger = logging.getLogger(__name__)
settings = get_settings()

CURRENCY_SYMBOL = {
    "USD": "$", "EUR": "€", "GBP": "£", "HKD": "HK$",
    "CZK": "CZK", "NOK": "kr", "DKK": "kr",
}

TICKER_EXTRACTION_PROMPT = """Jsi finanční analytik. Z níže uvedených zpráv a článků extrahuj všechny zmíněné akciové tickery.

Pravidla:
- US akcie: standardní ticker (NVDA, AAPL, META, ...)
- Německé akcie: ticker.DE (RHM.DE, VOW3.DE, ...)
- Londýnská burza: ticker.L (WIZZ.L, ...)
- Hongkong: číslice.HK (1810.HK, 700.HK, ...)
- Pokud je zmíněn název firmy, přelož ho na ticker (Rheinmetall → RHM.DE, Xiaomi → 1810.HK, Nvidia → NVDA)
- Ignoruj ETF, indexy a makro tickery (SPY, QQQ, GLD, TLT, VIX, USD, EUR, ...)
- Nikdy nevracej obyčejná anglická slova z headline nebo snippetů (např. STOCK, GROUP, TRUST, ALERT, DEAL, RATES, SLIPS, DROPS)

Vrať POUZE JSON array tickerů, nic jiného. Příklad: ["NVDA", "RHM.DE", "1810.HK", "AAPL"]
Pokud nic nenajdeš, vrať: []"""


SIGNAL_SEARCHES = [
    ("biggest movers gainers losers stock market today", "market_mover"),
    ("earnings beat surprise strong results quarterly report today", "earnings_beat"),
    ("analyst upgrade initiation buy rating stock today", "analyst_upgrade"),
    ("European stocks news movers today", "eu_mover"),
    ("Hong Kong China stocks news movers today", "hk_mover"),
    ("breakout momentum trending stocks today", "momentum"),
    ("short squeeze high volume unusual activity stock", "volume_spike"),
]

TICKER_REGEX = re.compile(r"\b(?:[0-9]{4}\.HK|[A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b")
US_TICKER_REGEX = re.compile(r"^[A-Z]{1,5}$")
EU_HK_SUFFIXES = (".DE", ".L", ".F", ".OL", ".HK", ".PA", ".AS", ".SW", ".ST", ".CO", ".HE", ".BR", ".MI", ".MC", ".VI", ".WA")
TICKER_STOPWORDS = {
    "AI", "ALL", "AND", "ARE", "ATH", "CEO", "CFO", "ETF", "EPS", "EUR",
    "FDA", "GDP", "GLD", "HK", "IPO", "NYSE", "QQQ", "SEC", "SPY", "TLT",
    "USD", "VIX", "WSJ",
}
TICKER_NOISE_WORDS = {
    "ABOUT", "ABOVE", "ACQUI", "AFTER", "ALERT", "BREAK", "CHINA", "CLOSE",
    "DAY", "DEAL", "DROPS", "EROCK", "FRESH", "GROUP", "GROUPS", "INDEX",
    "IRAN", "JUN", "LOWER", "MAJOR", "MARKET", "MARKETS", "MOVER", "MOVERS",
    "NEWS", "OPEN", "OTHER", "PRICE", "PRICES", "RATES", "REPORT", "RISES",
    "SHARE", "SHARES", "SLIPS", "SNAPS", "SOUTH", "STOCK", "STOCKS", "TODAY",
    "TOTAL", "TREND", "TRUST", "UNDER", "VALUE", "WEIGH",
}
ALPHA_VANTAGE_MIN_PRICE = 5.0
ALPHA_VANTAGE_MIN_VOLUME = 500_000
ALPHA_VANTAGE_MIN_MOVE_PCT = 3.0
SEARCH_SIGNAL_BASE_SCORES = {
    "market_mover": 1.0,
    "earnings_beat": 1.6,
    "analyst_upgrade": 1.4,
    "eu_mover": 1.8,
    "hk_mover": 1.8,
    "momentum": 1.3,
    "volume_spike": 1.2,
}
SUFFIX_CURRENCY_MAP = {
    ".HK": "HKD",
    ".L": "GBP",
    ".PA": "EUR",
    ".AS": "EUR",
    ".DE": "EUR",
    ".F": "EUR",
    ".MI": "EUR",
    ".MC": "EUR",
    ".HE": "EUR",
    ".BR": "EUR",
    ".SW": "CHF",
    ".ST": "SEK",
    ".OL": "NOK",
    ".CO": "DKK",
    ".VI": "EUR",
    ".WA": "PLN",
}


@dataclass
class SignalTicker:
    ticker: str
    signal_type: str
    signal_reason: str
    market: str = "US"
    signal_score: float = 1.0


@dataclass
class Candidate:
    ticker: str
    play_type: str
    confidence: int
    thesis: str
    entry_rationale: str
    exit_conditions: str
    invalidation_conditions: str
    profit_taking_plan: str
    holding_horizon: str
    monitoring_focus: str
    portfolio_fit_note: str
    recommended_size_czk: float
    add_reserve_czk: float
    market: str = "US"
    sector: str = ""
    industry: str = ""
    exchange: str = ""
    currency: str = "USD"
    current_price: Optional[float] = None
    recommended_shares: Optional[int] = None
    reserve_shares: Optional[int] = None



CLASSIFICATION_PROMPT = """Jsi portfolio analytik. Na základě informací o akci rozhodni:

1. Typ příležitosti:
   - A: fundamentální long — solidní byznys, atraktivní valuace, silný balance sheet
   - B: katalyzátor/narrativ — konkrétní spouštěč (earnings beat, partnership, re-rating sektoru)
   - C: momentum — silný technický trend na velkém objemu, jedeme s trhem

2. Úroveň přesvědčení (buď přísný, většina akcií je 2-3):
   - 1: spekulativní — slabé fundamenty nebo technicals, jen zajímavý signal
   - 2: explorační — jeden silný důvod, ale chybí potvrzení z více zdrojů
   - 3: střední — více shodujících se indikátorů (technicals + fundamentals + narrativ)
   - 4: silné — vše se shoduje: technicals bullish, fundamentals solidní, jasný katalyzátor, momentum potvrzuje. Dávej pouze výjimečně.

3. Krátká investiční teze (max 45 slov, česky)
4. Invalidation podmínky (max 30 slov)
5. Profit-taking plán (max 35 slov)
6. Holding horizon (max 15 slov)
7. Monitoring focus (max 25 slov)
8. Důvod vstupu (max 20 slov, 1 věta)

Pravidla pro exit podle typu hry:
- Type A: hlavní osa je thesis break nebo thesis delivered. Nepiš jen technický stop-loss.
- Type B: hlavní osa je catalyst played out / catalyst failed / time condition.
- Type C: hlavní osa je aktivní staged profit-taking + rychlá invalidace při ztrátě momentum.

KRITICKÉ:
- Vrať POUZE jeden JSON objekt.
- Bez markdownu, bez code fence, bez vysvětlení před ani po JSON.
- Buď velmi stručný. Neopakuj stejné informace mezi poli.

Odpověz ve formátu JSON:
{"play_type": "A|B|C", "confidence": 1-4, "thesis": "...", "invalidation_conditions": "...", "profit_taking_plan": "...", "holding_horizon": "...", "monitoring_focus": "...", "entry_rationale": "..."}

Pokud akcie nesplňuje kritéria (meme, pink sheet, bez teze), odpověz: {"skip": true}

Nepoužívej emojis v žádném z textových polí."""


def _search_signal_score(signal_type: str, market: str) -> float:
    base = SEARCH_SIGNAL_BASE_SCORES.get(signal_type, 1.0)
    if market == "EU_HK":
        base += 0.4
    return base


def _infer_currency(ticker: str, fundamentals: dict) -> str:
    currency = (fundamentals.get("currency") or "").upper().strip()
    if currency:
        return currency

    if "." in ticker:
        _, suffix = ticker.rsplit(".", 1)
        mapped = SUFFIX_CURRENCY_MAP.get(f".{suffix.upper()}")
        if mapped:
            return mapped

    return "USD"


async def _extract_tickers_with_llm(articles_text: str, signal_type: str, signal_reason: str) -> List[SignalTicker]:
    """Ask Claude to extract tickers from article content. Handles company names, EU/HK formats."""
    try:
        response = await call_llm(TICKER_EXTRACTION_PROMPT, articles_text[:3000], max_tokens=300, label=f'ticker_extraction:{signal_type}')
        # Parse JSON array from response
        import re
        match = re.search(r'\[.*?\]', response, re.DOTALL)
        if not match:
            return []
        tickers = json.loads(match.group())
        result = []
        for ticker in tickers:
            normalized = _normalize_search_ticker_candidate(ticker)
            if normalized:
                market = "EU_HK" if any(normalized.endswith(s) for s in EU_HK_SUFFIXES) else "US"
                result.append(SignalTicker(
                    ticker=normalized,
                    signal_type=signal_type,
                    signal_reason=signal_reason,
                    market=market,
                    signal_score=_search_signal_score(signal_type, market),
                ))
        return result
    except Exception as e:
        logger.warning("LLM ticker extraction failed for %s: %s", signal_type, e)
        return []


def _extract_tickers_with_regex(articles_text: str, signal_type: str, signal_reason: str) -> List[SignalTicker]:
    """Cheap fallback when the LLM extractor returns nothing useful."""
    result: List[SignalTicker] = []
    seen: set[str] = set()

    for match in TICKER_REGEX.findall(articles_text.upper()):
        ticker = _normalize_search_ticker_candidate(match)
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        market = "EU_HK" if any(ticker.endswith(s) for s in EU_HK_SUFFIXES) else "US"
        result.append(SignalTicker(
            ticker=ticker,
            signal_type=signal_type,
            signal_reason=signal_reason,
            market=market,
            signal_score=_search_signal_score(signal_type, market),
        ))

    return result


async def _extract_signals_from_search(articles_text: str, signal_type: str, signal_reason: str) -> List[SignalTicker]:
    extracted = await _extract_tickers_with_llm(articles_text, signal_type, signal_reason)
    if extracted:
        return extracted
    return _extract_tickers_with_regex(articles_text, signal_type, signal_reason)


async def _validate_tickers(tickers: List[SignalTicker], redis) -> List[SignalTicker]:
    """Quick yfinance validation — filter out tickers that don't exist or are garbage."""
    semaphore = asyncio.Semaphore(max(1, settings.search_max_concurrency))

    async def _validate(sig: SignalTicker) -> Optional[SignalTicker]:
        async with semaphore:
            try:
                fundamentals = await get_fundamentals(redis, sig.ticker)
                if is_valid_stock(fundamentals):
                    return sig
            except Exception:
                return None
        return None

    validated = await asyncio.gather(*(_validate(sig) for sig in tickers))
    return [sig for sig in validated if sig]


def _merge_signal(existing: SignalTicker, incoming: SignalTicker) -> None:
    existing.signal_score += incoming.signal_score
    if incoming.signal_type not in existing.signal_type.split(", "):
        existing.signal_type = f"{existing.signal_type}, {incoming.signal_type}"
    if incoming.signal_reason and incoming.signal_reason not in existing.signal_reason:
        existing.signal_reason = f"{existing.signal_reason} | {incoming.signal_reason}"[:220]


def _add_signals_to_map(signal_map: dict[str, SignalTicker], signals: List[SignalTicker]) -> None:
    for sig in signals:
        if sig.ticker in signal_map:
            _merge_signal(signal_map[sig.ticker], sig)
        else:
            signal_map[sig.ticker] = sig


def _safe_float(value) -> Optional[float]:
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def _safe_int(value) -> Optional[int]:
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


def _normalize_search_ticker_candidate(raw_ticker: Any) -> Optional[str]:
    if not isinstance(raw_ticker, str):
        return None

    ticker = raw_ticker.strip().upper().strip(".,:;!?)(")
    if not ticker:
        return None
    if ticker in TICKER_STOPWORDS or ticker in TICKER_NOISE_WORDS:
        return None

    if "." in ticker:
        _, suffix = ticker.rsplit(".", 1)
        normalized = f".{suffix}"
        if normalized not in EU_HK_SUFFIXES:
            return None
        if normalized == ".HK":
            return ticker if re.fullmatch(r"[0-9]{4}\.HK", ticker) else None
        return ticker if re.fullmatch(r"[A-Z]{1,5}\.[A-Z]{1,3}", ticker) else None

    if not US_TICKER_REGEX.fullmatch(ticker):
        return None
    if ticker in TICKER_NOISE_WORDS:
        return None
    return ticker


def _is_supported_alpha_vantage_ticker(ticker: str) -> bool:
    normalized = _normalize_search_ticker_candidate(ticker)
    if not normalized or not US_TICKER_REGEX.fullmatch(normalized):
        return False
    return True


def _extract_signals_from_alpha_vantage(payload: dict) -> List[SignalTicker]:
    if not payload:
        return []

    signals: List[SignalTicker] = []
    sections = [
        ("top_gainers", "top_gainer", 3.0),
        ("top_losers", "top_loser", 2.5),
        ("most_actively_traded", "most_active", 2.0),
    ]

    for field, signal_type, base_score in sections:
        for item in payload.get(field, []):
            ticker = str(item.get("ticker", "")).strip().upper()
            price = _safe_float(item.get("price"))
            volume = _safe_int(item.get("volume"))
            change_pct = _safe_float(item.get("change_percentage"))

            if not _is_supported_alpha_vantage_ticker(ticker):
                continue
            if price is None or price < ALPHA_VANTAGE_MIN_PRICE:
                continue
            if volume is None or volume < ALPHA_VANTAGE_MIN_VOLUME:
                continue
            if field != "most_actively_traded" and (change_pct is None or abs(change_pct) < ALPHA_VANTAGE_MIN_MOVE_PCT):
                continue

            score_bonus = min((abs(change_pct or 0) / 25.0), 2.0) + min(volume / 100_000_000, 1.5)
            direction = "růst" if (change_pct or 0) >= 0 else "pokles"
            reason = f"Alpha Vantage {signal_type}: {direction} {change_pct or 0:.1f}% na objemu {volume:,}"

            signals.append(SignalTicker(
                ticker=ticker,
                signal_type=signal_type,
                signal_reason=reason,
                market="US",
                signal_score=base_score + score_bonus,
            ))

    return signals


async def _augment_with_news_searches(signal_map: dict[str, SignalTicker]) -> None:
    today = date.today().isoformat()

    for query_template, signal_type in SIGNAL_SEARCHES:
        query = f"{query_template} {today}"
        try:
            results = await search(query, max_results=5, days=2)
            log_event(logger, logging.INFO, 'signal_search_completed', signal_type=signal_type, query=query[:80], results=len(results))
            if not results:
                continue

            combined = "\n\n".join(
                f"[{r.get('title', '')}]\n{r.get('content', '')[:400]}"
                for r in results
            )
            reason = results[0].get("title", signal_type)[:80]
            new_signals = await _extract_signals_from_search(combined, signal_type, reason)
            _add_signals_to_map(signal_map, new_signals)
        except Exception as e:
            logger.warning("Signal search failed for '%s': %s", signal_type, e)
            continue


async def run_signal_scan(redis) -> List[SignalTicker]:
    """
    Stage 1 — multi-source discovery. No hardcoded ticker lists.
    Alpha Vantage movers + news/search signals → yfinance validation.
    """
    signal_map: dict[str, SignalTicker] = {}

    try:
        mover_payload = await get_top_movers(redis)
        mover_signals = _extract_signals_from_alpha_vantage(mover_payload)
        _add_signals_to_map(signal_map, mover_signals)
        logger.info('Stage 1 Alpha Vantage signals: %d', len(mover_signals))
        log_event(logger, logging.INFO, 'stage1_alpha_vantage_completed', signals=len(mover_signals))
    except Exception as e:
        logger.warning("Alpha Vantage movers failed: %s", e)

    logger.info("Stage 1 augmenting with search signals (current=%d)", len(signal_map))
    await _augment_with_news_searches(signal_map)

    # Validate with yfinance — filter out non-existent/garbage tickers
    all_signals = list(signal_map.values())
    logger.info("Stage 1 raw signals: %d — validating...", len(all_signals))
    valid_signals = await _validate_tickers(all_signals, redis)
    valid_signals.sort(key=lambda sig: sig.signal_score, reverse=True)
    logger.info('Stage 1 validated: %d signals', len(valid_signals))
    log_event(logger, logging.INFO, 'stage1_completed', raw_signals=len(all_signals), validated_signals=len(valid_signals))

    return valid_signals



async def run_deep_filter_with_diagnostics(
    signals: List[SignalTicker],
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    redis,
    user_id: str,
) -> tuple[List[Candidate], dict[str, Any]]:
    """Stage 2 — filter top 15 signals to 5-10 actionable candidates with thesis."""
    top_signals = sorted(signals, key=lambda s: s.signal_score, reverse=True)[:15]
    held = {p.ticker for p in portfolio.positions}

    from app.services.portfolio_service import get_settings
    fx_rates = await get_fx_rates(redis)

    settings = get_settings(user_id)
    max_positions = int(settings.get("max_positions", 20))
    total_portfolio_value = portfolio.total_value_czk
    base_size_czk = total_portfolio_value * 0.80 / max_positions
    log_event(
        logger,
        logging.INFO,
        'stage2_sizing_context',
        total_portfolio_value=round(total_portfolio_value, 2),
        cash_czk=round(portfolio.cash_czk, 2),
        max_positions=max_positions,
        base_size_czk=round(base_size_czk, 2),
        market_regime=market_context.market_regime,
    )

    diagnostics: dict[str, Any] = {
        "top_signals_count": len(top_signals),
        "held_skipped": 0,
        "invalid_stock_skipped": 0,
        "llm_skip": 0,
        "bear_regime_skipped": 0,
        "exception_skipped": 0,
        "watchlist_adds": 0,
        "candidates_found": 0,
        "rejection_counts": {},
        "rejections": [],
    }

    def record_rejection(reason: str, ticker: str, detail: str | None = None) -> None:
        diagnostics["rejection_counts"][reason] = diagnostics["rejection_counts"].get(reason, 0) + 1
        diagnostics["rejections"].append({
            "ticker": ticker,
            "reason": reason,
            "detail": detail,
        })

    candidates: List[Candidate] = []
    watchlist_adds: List[dict] = []

    for sig in top_signals:
        ticker = sig.ticker
        if ticker in held:
            diagnostics['held_skipped'] += 1
            record_rejection('already_held', ticker)
            log_event(logger, logging.INFO, 'stage2_ticker_skipped', ticker=ticker, reason='already_held')
            continue

        try:
            fundamentals = await get_fundamentals(redis, ticker)
            if not is_valid_stock(fundamentals):
                diagnostics['invalid_stock_skipped'] += 1
                record_rejection('invalid_stock', ticker)
                log_event(logger, logging.INFO, 'stage2_ticker_skipped', ticker=ticker, reason='invalid_stock')
                continue

            technicals = await get_technicals(redis, ticker)
            upcoming = await get_upcoming_earnings(redis, [ticker], days=7)
            has_upcoming_earnings = ticker in upcoming

            news_results = await search(f"{ticker} stock news analysis", max_results=3, days=14)
            news_context = format_results(news_results)

            fit_note = _check_portfolio_fit(ticker, fundamentals, portfolio)
            bear_regime = market_context.market_regime == "bear"

            context_for_llm = f"""Ticker: {ticker} ({sig.market})
Signal: {sig.signal_type} — {sig.signal_reason}
Fundamentals: PE={fundamentals.get('pe')}, revenue_growth={fundamentals.get('revenue_growth')}, sector={fundamentals.get('sector')}, country={fundamentals.get('country')}, market_cap={fundamentals.get('market_cap')}
Technicals: RSI={technicals.get('rsi14')}, trend={technicals.get('trend_signal')}, SMA50={technicals.get('sma50')}, SMA200={technicals.get('sma200')}
Upcoming earnings (7d): {'ANO' if has_upcoming_earnings else 'NE'}
Market regime: {market_context.market_regime} (sentiment score: {market_context.fng_score})
Portfolio fit: {fit_note}

News:
{news_context[:600]}"""

            response_text = await call_llm(CLASSIFICATION_PROMPT, context_for_llm, max_tokens=700, label=f'stage2_classification:{ticker}')
            classification = _parse_classification(response_text)

            if not classification:
                diagnostics['llm_skip'] += 1
                record_rejection('llm_parse_failed', ticker, _preview_llm_response(response_text))
                log_event(
                    logger,
                    logging.WARNING,
                    'stage2_ticker_skipped',
                    ticker=ticker,
                    reason='llm_parse_failed',
                    response_preview=_preview_llm_response(response_text),
                )
                watchlist_adds.append({
                    "ticker": ticker,
                    "stage": "watching",
                    "signal_reason": sig.signal_reason,
                    "theme": None,
                })
                continue

            if classification.get("skip"):
                diagnostics['llm_skip'] += 1
                record_rejection('llm_skip', ticker)
                log_event(logger, logging.INFO, 'stage2_ticker_skipped', ticker=ticker, reason='llm_skip')
                watchlist_adds.append({
                    "ticker": ticker,
                    "stage": "watching",
                    "signal_reason": sig.signal_reason,
                    "theme": None,
                })
                continue

            confidence = classification.get("confidence", 2)
            play_type = classification.get("play_type", "A")

            if bear_regime and confidence <= 1:
                diagnostics['bear_regime_skipped'] += 1
                record_rejection('bear_regime_low_confidence', ticker, f'confidence={confidence}')
                log_event(logger, logging.INFO, 'stage2_ticker_skipped', ticker=ticker, reason='bear_regime_low_confidence', confidence=confidence)
                watchlist_adds.append({
                    "ticker": ticker,
                    "stage": "candidate",
                    "signal_reason": f"Bear regime — confidence je příliš nízká. {sig.signal_reason}",
                    "theme": fundamentals.get("sector"),
                })
                continue

            if bear_regime and play_type == "C" and confidence < 3:
                diagnostics['bear_regime_skipped'] += 1
                record_rejection('bear_regime_momentum', ticker, f'confidence={confidence}')
                log_event(logger, logging.INFO, 'stage2_ticker_skipped', ticker=ticker, reason='bear_regime_momentum', confidence=confidence)
                watchlist_adds.append({
                    "ticker": ticker,
                    "stage": "candidate",
                    "signal_reason": f"Bear regime — momentum setup bez dost silné confidence. {sig.signal_reason}",
                    "theme": fundamentals.get("sector"),
                })
                continue

            confidence_multiplier = {4: 1.3, 3: 1.0, 2: 0.75, 1: 0.5}.get(confidence, 1.0)
            if bear_regime:
                confidence_multiplier *= 0.7
            size_czk = round(base_size_czk * confidence_multiplier / 1000) * 1000
            reserve_ratio = {4: 0.60, 3: 0.60, 2: 0.50, 1: 0.0}.get(confidence, 0.5)
            if bear_regime:
                reserve_ratio = min(reserve_ratio, 0.35)
            reserve_czk = round(size_czk * reserve_ratio / 1000) * 1000

            currency = _infer_currency(ticker, fundamentals)
            price_local = technicals.get("price")
            recommended_shares: Optional[int] = None
            reserve_shares: Optional[int] = None
            fx_rate = get_fx_rate(currency, fx_rates)
            if price_local and price_local > 0 and fx_rate > 0:
                price_czk = price_local * fx_rate
                recommended_shares = int(size_czk / price_czk)
                size_czk = round(recommended_shares * price_czk)
                if reserve_czk > 0:
                    reserve_shares = int(reserve_czk / price_czk)
                    reserve_czk = round(reserve_shares * price_czk)

            theme = fundamentals.get("sector")

            log_event(logger, logging.INFO, 'stage2_candidate_accepted', ticker=ticker, play_type=play_type, confidence=confidence, sector=theme, bear_regime=bear_regime)

            candidates.append(Candidate(
                ticker=ticker,
                play_type=play_type,
                confidence=confidence,
                thesis=classification.get("thesis", ""),
                entry_rationale=classification.get("entry_rationale", ""),
                exit_conditions=classification.get("invalidation_conditions", "") or classification.get("exit_conditions", ""),
                invalidation_conditions=classification.get("invalidation_conditions", "") or classification.get("exit_conditions", ""),
                profit_taking_plan=classification.get("profit_taking_plan", ""),
                holding_horizon=classification.get("holding_horizon", ""),
                monitoring_focus=classification.get("monitoring_focus", ""),
                portfolio_fit_note=fit_note,
                recommended_size_czk=size_czk,
                add_reserve_czk=reserve_czk,
                market=sig.market,
                sector=fundamentals.get("sector") or "",
                industry=fundamentals.get("industry") or "",
                exchange=fundamentals.get("exchange") or "",
                currency=currency,
                current_price=price_local,
                recommended_shares=recommended_shares,
                reserve_shares=reserve_shares,
            ))

            watch_reason = classification.get("entry_rationale") or sig.signal_reason
            watchlist_adds.append({
                "ticker": ticker,
                "stage": "candidate",
                "signal_reason": watch_reason,
                "theme": theme,
            })

        except Exception as e:
            diagnostics['exception_skipped'] += 1
            record_rejection('exception', ticker, str(e))
            log_event(logger, logging.WARNING, 'stage2_ticker_exception', ticker=ticker, error=str(e), error_type=type(e).__name__)
            logger.warning('Deep filter failed for %s: %s', ticker, e)
            continue

    for item in watchlist_adds:
        try:
            await add_or_update_watchlist(
                user_id=user_id,
                ticker=item["ticker"],
                stage=item["stage"],
                signal_reason=item["signal_reason"],
                theme=item.get("theme"),
            )
        except Exception as e:
            logger.warning("Watchlist update failed for %s: %s", item["ticker"], e)

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    trimmed_candidates = candidates[:8]
    diagnostics["watchlist_adds"] = len(watchlist_adds)
    diagnostics["candidates_found"] = len(trimmed_candidates)
    logger.info('Stage 2: %d candidates from %d signals', len(trimmed_candidates), len(top_signals))
    log_event(logger, logging.INFO, 'stage2_completed', top_signals=len(top_signals), candidates=len(trimmed_candidates), rejection_counts=diagnostics['rejection_counts'])
    return trimmed_candidates, diagnostics


async def run_deep_filter(
    signals: List[SignalTicker],
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    redis,
    user_id: str,
) -> List[Candidate]:
    candidates, _ = await run_deep_filter_with_diagnostics(
        signals,
        portfolio,
        market_context,
        redis,
        user_id,
    )
    return candidates


def _check_portfolio_fit(ticker: str, fundamentals: dict, portfolio: PortfolioSnapshot) -> str:
    sector = fundamentals.get("sector")
    if sector and portfolio.sector_exposure.get(sector, 0) > 20:
        return f"Sektor '{sector}' přetížený ({portfolio.sector_exposure[sector]:.0f}%) — zvažit."
    if len(portfolio.positions) >= 20:
        return "Portfolio plné (20/20) — nutná rotace."
    return "Fit OK"


def _parse_classification(text: str) -> Optional[dict]:
    import re

    cleaned = (text or "").strip()
    if not cleaned:
        return None

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    try:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None


def _preview_llm_response(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
