"""
Daily report generator — Czech, AG-inspired format.
Multi-currency aware. Batches DB calls.
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional

from app.services.portfolio_service import PortfolioSnapshot
from app.services.market.market_context import MarketContext
from app.services.market.earnings import get_upcoming_earnings
from app.services.market.technical import get_technicals
from app.agent.watchlist_manager import get_active_watchlist
from app.ai.client import call_llm
from app.search.client import search
from app.core.run_logging import log_event
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

COMMENTARY_PROMPT = """Jsi stručný investiční komentátor. Na základě dat portfolia napiš MAXIMÁLNĚ 3 věty komentáře k dnešnímu dnu. Zaměř se na největší pohyby a hlavní rizika. Česky. Nepoužívej emojis."""

MARKET_SUMMARY_PROMPT = """Jsi tržní analytik. Na základě níže uvedených zpravodajských titulků napiš 1-2 věty shrnující co dnes hýbe trhem — hlavní témata, sentiment, klíčové pohyby. Buď konkrétní, vyhni se obecnostem. Česky. Nepoužívej emojis."""

CONFIDENCE_LABELS = {4: "4/4", 3: "3/4", 2: "2/4", 1: "1/4"}
THESIS_BADGES = {
    "intact": "intact",
    "weakening": "weakening",
    "zombie": "zombie",
    "invalidated": "invalidated",
    "delivered": "delivered",
}
CURRENCY_SYMBOL = {
    "USD": "$", "EUR": "€", "GBP": "£", "HKD": "HK$",
    "CZK": "Kč", "NOK": "kr", "DKK": "kr",
}
TITLE_DATE_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
GENERIC_MARKET_NEWS_PHRASES = (
    "stock market news for",
    "global stock market news",
    "world indices coverage",
    "historical data",
)

SENTIMENT_LABELS_CS = {
    "extreme_fear": "extrémní strach",
    "fear": "strach",
    "neutral": "neutrální",
    "greed": "chamtivost",
    "extreme_greed": "extrémní chamtivost",
}


def _fmt_price(price: Optional[float], currency: str = "USD") -> str:
    if price is None:
        return "—"
    sym = CURRENCY_SYMBOL.get(currency, currency + " ")
    return f"{sym}{price:.2f}"


def _parse_result_datetime(raw_value: Optional[str]) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        if "T" in raw_value:
            dt = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        else:
            dt = parsedate_to_datetime(raw_value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _contains_stale_title_date(title: str, now: datetime) -> bool:
    match = TITLE_DATE_RE.search(title or "")
    if not match:
        return False
    try:
        parsed = datetime.strptime(match.group(0), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.strptime(match.group(0), "%b %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return False
    return parsed.date() < now.date()


def _is_generic_market_roundup(title: str) -> bool:
    lowered = (title or "").strip().lower()
    return any(phrase in lowered for phrase in GENERIC_MARKET_NEWS_PHRASES)


def _select_fresh_market_news(results: List[dict], now: datetime) -> List[dict]:
    fresh_cutoff = now - timedelta(hours=30)
    fresh_results: List[tuple[int, datetime, dict]] = []

    for result in results:
        title = result.get("title", "") or ""
        published_at = _parse_result_datetime(result.get("published_at") or result.get("published_date"))

        if _contains_stale_title_date(title, now):
            continue
        if _is_generic_market_roundup(title):
            continue
        if published_at and published_at < fresh_cutoff:
            continue

        freshness_rank = 0 if published_at else 1
        freshness_dt = published_at or now
        fresh_results.append((freshness_rank, freshness_dt, result))

    fresh_results.sort(key=lambda item: (item[0], -item[1].timestamp()))
    return [item[2] for item in fresh_results[:3]]


def _format_sentiment_label(label: Optional[str]) -> str:
    if not label:
        return "—"
    return SENTIMENT_LABELS_CS.get(label, label)


def _batch_load_theses(user_id: str, position_ids: List[str]) -> Dict[str, str]:
    """Load thesis statuses for all positions in one query."""
    if not position_ids:
        return {}
    db = get_supabase()
    response = (
        db.table("theses")
        .select("position_id, status")
        .eq("user_id", user_id)
        .in_("position_id", position_ids)
        .order("created_at", desc=True)
        .execute()
    )
    # Keep first (latest) per position_id
    result: Dict[str, str] = {}
    for row in (response.data or []):
        pid = row["position_id"]
        if pid not in result:
            result[pid] = row["status"]
    return result


async def generate_report(
    portfolio: PortfolioSnapshot,
    recommendations: List[dict],
    position_flags,
    market_context: MarketContext,
    discovery_log: dict,
    redis,
    user_id: str,
) -> str:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%-d. %-m. %Y")
    time_str = now.strftime("%H:%M UTC")

    # Batch-load all thesis statuses upfront
    position_ids = [p.id for p in portfolio.positions]
    thesis_statuses = _batch_load_theses(user_id, position_ids)

    parts = []

    # HEADER
    parts.append(f"# SwingScout Report — {date_str}")
    parts.append(f"*Aktuálně {date_str} | {time_str}*\n")

    # STATS
    pnl_sign = "+" if portfolio.total_pnl_czk >= 0 else ""
    ret_sign = "+" if portfolio.total_return_pct >= 0 else ""
    parts.append("## Stav portfolia\n")
    parts.append("| Equity | P/L celkem | Výkon od startu | Cash |")
    parts.append("|--------|-----------|-----------------|------|")
    parts.append(
        f"| **{portfolio.total_value_czk:,.0f} Kč** "
        f"| {pnl_sign}{portfolio.total_pnl_czk:,.0f} Kč ({pnl_sign}{portfolio.total_pnl_pct:.1f}%) "
        f"| {ret_sign}{portfolio.total_return_pct:.2f}% "
        f"| {portfolio.cash_czk:,.0f} Kč |\n"
    )

    # DNEŠNÍ ROZHODNUTÍ + kompaktní tabulka doporučení
    decision = _build_decision(recommendations, position_flags)
    parts.append("## Dnešní rozhodnutí\n")
    parts.append(f"### {decision['headline']}\n")
    if recommendations:
        play_type_labels = {"A": "Fundamental", "B": "Katalyzátor", "C": "Momentum"}
        parts.append("| Ticker | Akce | Typ | Velikost | Konf. |")
        parts.append("|--------|------|-----|---------|-------|")
        for rec in recommendations:
            stars = CONFIDENCE_LABELS.get(rec["confidence"], "—")
            action_label = {
                "buy": "Koupit", "sell": "Prodat", "add": "Přikoupit",
                "exit": "Exit", "csp": "CSP", "long_call": "Long Call",
            }.get(rec["action"], rec["action"].upper())
            play_label = play_type_labels.get(rec["play_type"], rec["play_type"])
            size = f"{rec['recommended_size_czk']:,.0f} Kč" if rec.get("recommended_size_czk") else "—"
            parts.append(f"| **{rec['ticker']}** | {action_label} | {play_label} | {size} | {stars} |")
    parts.append("")

    # HOLDINGS TABLE
    parts.append("## Portfolio\n")
    parts.append("| Ticker | Ks | Vstup | Aktuální | % | P/L Kč | Teze |")
    parts.append("|--------|-----|-------|---------|---|---------|------|")

    for pos in sorted(portfolio.positions, key=lambda p: abs(p.unrealized_pnl_czk), reverse=True):
        chg = f"{pos.change_pct:+.1f}%" if pos.change_pct is not None else "—"
        pnl = f"{pos.unrealized_pnl_czk:+,.0f}"
        price_str = _fmt_price(pos.current_price, pos.currency)
        avg_str = _fmt_price(pos.avg_cost, pos.currency)
        status = thesis_statuses.get(pos.id, "intact")
        badge = THESIS_BADGES.get(status, status)
        flag = " (!)" if any(f.ticker == pos.ticker and f.urgency == "high" for f in position_flags) else ""
        parts.append(
            f"| **{pos.ticker}**{flag} | {pos.shares:.0f} "
            f"| {avg_str} | {price_str} | {chg} | {pnl} | {badge} |"
        )
    parts.append("")

    # CO HÝBE TRHEM
    try:
        raw_market_news = await search("global stock market news today major moves", max_results=6, days=1)
        market_news = _select_fresh_market_news(raw_market_news, now)
        parts.append("## Co dnes hýbe trhem\n")

        fng_spike_note = " — sentiment spike, zvaž parciální výběr" if market_context.fng_spike else ""
        parts.append(
            f"**{market_context.market_regime.upper()}** "
            f"| Sentiment: {market_context.fng_score or '—'} ({_format_sentiment_label(market_context.fng_label)})"
            f"{fng_spike_note}\n"
        )

        if market_news:
            news_titles = "\n".join(
                f"- [{r.get('provider', 'search')}] {r.get('title', '')}"
                f" | published: {r.get('published_at') or r.get('published_date') or 'unknown'}"
                f" | {(r.get('content', '') or '')[:150]}"
                for r in market_news[:3]
            )
            try:
                market_summary = await call_llm(MARKET_SUMMARY_PROMPT, news_titles, max_tokens=120, label='report_market_summary')
                parts.append(market_summary)
                parts.append("")
            except Exception as e:
                logger.warning("Market summary LLM failed: %s", e)

            for r in market_news[:3]:
                title = r.get("title", "")
                url = r.get("url", "")
                if url:
                    parts.append(f"- [{title}]({url})")
                else:
                    parts.append(f"- {title}")

        parts.append("")
    except Exception as e:
        logger.warning("Market news failed: %s", e)

    # COMMENTARY
    try:
        summary = _build_portfolio_summary(portfolio, position_flags)
        commentary = await call_llm(COMMENTARY_PROMPT, summary, max_tokens=150, label='report_commentary')
        parts.append("## Komentář\n")
        parts.append(commentary)
        parts.append("")
    except Exception as e:
        logger.warning("Commentary failed: %s", e)

    # TOP PLUS / TOP MÍNUS
    sorted_pos = sorted(portfolio.positions, key=lambda p: p.unrealized_pnl_czk)
    parts.append("## Top plus / Top mínus\n")
    parts.append("**Top plus:**")
    for p in reversed(sorted_pos[-3:]):
        if p.unrealized_pnl_czk > 0:
            parts.append(f"- **{p.ticker}**: +{p.unrealized_pnl_czk:,.0f} Kč")
    parts.append("\n**Top mínus:**")
    for p in sorted_pos[:3]:
        if p.unrealized_pnl_czk < 0:
            parts.append(f"- **{p.ticker}**: {p.unrealized_pnl_czk:,.0f} Kč")
    parts.append("")

    # CO HLÍDAT
    parts.append("## Co hlídat\n")

    # Earnings
    try:
        tickers = [p.ticker for p in portfolio.positions]
        upcoming = await get_upcoming_earnings(redis, tickers, days=7)
        if upcoming:
            for ticker, d in upcoming.items():
                parts.append(f"- **{ticker}** earnings {d.strftime('%-d. %-m.')} — připravit exit/hold rozhodnutí")
    except Exception as e:
        logger.warning("Earnings calendar failed: %s", e)

    # Pozice blízko SMA50 (stop-loss zóna)
    try:
        for pos in portfolio.positions:
            if not pos.current_price:
                continue
            tech = await get_technicals(redis, pos.ticker)
            sma50 = tech.get("sma50")
            if sma50 and pos.current_price > 0:
                dist_pct = (pos.current_price - sma50) / sma50 * 100
                if 0 < dist_pct < 5:
                    parts.append(
                        f"- **{pos.ticker}** blízko SMA50 ({sma50:.2f}) — "
                        f"jen {dist_pct:.1f}% nad stop-loss zónou"
                    )
    except Exception as e:
        logger.warning("SMA50 proximity check failed: %s", e)

    # Makro hladiny
    try:
        MACRO = [
            ("CL=F", "Ropa (WTI)", "$", 0),
            ("^TNX", "10Y výnos", "", 2),
            ("^VIX", "VIX", "", 1),
        ]
        macro_lines = []
        for symbol, label, prefix, decimals in MACRO:
            tech = await get_technicals(redis, symbol)
            price = tech.get("price")
            if price:
                fmt = f"{prefix}{price:.{decimals}f}"
                trend = tech.get("trend_signal", "")
                trend_note = {
                    "strong_bullish": "↑↑", "bullish": "↑",
                    "strong_bearish": "↓↓", "bearish": "↓",
                }.get(trend, "")
                macro_lines.append(f"- **{label}:** {fmt} {trend_note}".strip())
        if macro_lines:
            parts.extend(macro_lines)
    except Exception as e:
        logger.warning("Macro levels failed: %s", e)

    if not any(l.startswith("- ") for l in parts[-10:]):
        parts.append("- Nic kritického k hlídání")

    parts.append("")

    # AGENT WATCHLIST
    try:
        watchlist = await get_active_watchlist(user_id)
        parts.append("## Agent watchlist\n")
        if watchlist:
            for item in watchlist[:5]:
                reason = item.get("signal_reason") or "—"
                parts.append(f"- **{item['ticker']}** — {reason}")
        else:
            parts.append("- Prázdný")
        parts.append("")
    except Exception as e:
        logger.warning("Watchlist failed: %s", e)

    # DISCOVERY LOG
    parts.append("## Discovery log\n")
    scanned = discovery_log.get("scanned_count", 0)
    signal_tickers = discovery_log.get("signal_tickers", [])
    n_candidates = discovery_log.get("candidates_found", 0)
    parts.append(f"Prošel jsem **{scanned}** tickerů.")
    if signal_tickers:
        sample = ", ".join(signal_tickers[:10])
        more = f" ... ({len(signal_tickers) - 10} dalších)" if len(signal_tickers) > 10 else ""
        parts.append(f"Signály: {sample}{more}")
    parts.append(f"Kandidátů po deep filtru: **{n_candidates}**")

    report = '\n'.join(parts)
    log_event(logger, logging.INFO, 'report_generated', sections=len(parts), recommendations=len(recommendations), warnings=discovery_log.get('warnings_count'), report_chars=len(report))
    return report


def _build_decision(recommendations: List[dict], flags) -> dict:
    has_buy = any(r["action"] in ("buy", "add") for r in recommendations)
    has_exit = any(r["action"] in ("exit", "sell") for r in recommendations)
    urgent = [f for f in flags if f.flag_type == "exit_now"]

    if urgent:
        headline = "URGENTNÍ EXIT"
        rules = [f.detail for f in urgent[:2]]
    elif has_buy and has_exit:
        headline = "ROTACE"
        buys = [f"Koupit {r['ticker']}" for r in recommendations if r["action"] == "buy"]
        exits = [f"Exit {r['ticker']}" for r in recommendations if r["action"] in ("exit", "sell")]
        rules = exits + buys
    elif has_buy:
        headline = "BUY"
        rules = [f"Koupit {r['ticker']}" for r in recommendations if r["action"] == "buy"]
    elif has_exit:
        headline = "EXIT"
        rules = [f"Exit {r['ticker']}" for r in recommendations if r["action"] in ("exit", "sell")]
    else:
        headline = "HOLD"
        rules = ["Bez obchodu", "Sledovat pozice"]

    return {"headline": headline, "rules": rules or ["Bez obchodu"]}


def _build_portfolio_summary(portfolio: PortfolioSnapshot, flags) -> str:
    top5 = sorted(portfolio.positions, key=lambda x: x.unrealized_pnl_pct, reverse=True)[:5]
    pos_summary = ", ".join(f"{p.ticker} ({p.unrealized_pnl_pct:+.1f}%)" for p in top5)
    flag_summary = ", ".join(f"{f.ticker}:{f.flag_type}" for f in flags[:5])
    return (
        f"Portfolio: {portfolio.total_value_czk:,.0f} Kč, "
        f"P/L {portfolio.total_pnl_pct:+.1f}%, cash {portfolio.cash_czk:,.0f} Kč\n"
        f"Top pozice: {pos_summary}\n"
        f"Flagy: {flag_summary or 'žádné'}"
    )
