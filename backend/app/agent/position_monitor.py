"""
Position monitor — thesis validity, zombie detection, add triggers, Type C exit.
Runs as part of daily_run and intraday_run.
"""
import logging
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from app.ai.client import call_llm
from app.services.portfolio_service import PortfolioSnapshot, PositionSnapshot
from app.services.market.market_context import MarketContext
from app.services.market.technical import get_technicals
from app.services.thesis_service import create_thesis_event
from app.search.client import format_results, search
from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

THESIS_CHECK_PROMPT = """Jsi denní portfolio monitor pro thesis-based swing portfolio.
Vyhodnoť, jestli původní teze pozice stále platí a zda je potřeba akce.

Vrať POUZE JSON:
{
  "status": "intact|weakening|invalidated|delivered|zombie",
  "action_bias": "hold|add_candidate|reduce_or_take_profit|exit_now|watch",
  "urgency": "normal|high",
  "summary": "jedna až dvě krátké věty česky"
}

Pravidla:
- Teze je hlavní contract. Nehodnoť jen podle ceny.
- Add_candidate pouze když teze zůstává intact a pokles vypadá jako příležitost, ne thesis break.
- Reduce_or_take_profit pouze když to sedí s původním profit-taking plánem nebo je catalyst z velké části odehraný.
- Exit_now pokud zprávy/fundamenty přímo narušují důvod nákupu nebo invalidation podmínky.
- Pokud nejsou čerstvé zprávy jasné, nehádej: status nech intact/weakening a action_bias watch/hold."""


@dataclass
class PositionFlag:
    ticker: str
    flag_type: str  # add_trigger | zombie | exit_now | thesis_delivered | partial_profit | news_alert
    detail: str
    urgency: str = "normal"  # normal | high


async def monitor_positions(
    portfolio: PortfolioSnapshot,
    market_context: MarketContext,
    redis,
    user_id: str,
) -> List[PositionFlag]:
    flags: List[PositionFlag] = []
    db = get_supabase()

    for pos in portfolio.positions:
        ticker = pos.ticker

        thesis_response = (
            db.table("theses")
            .select("*")
            .eq("user_id", user_id)
            .eq("position_id", pos.id)
            .execute()
        )
        thesis = thesis_response.data[0] if thesis_response.data else None
        thesis_status = thesis.get("status", "intact") if thesis else "intact"
        technicals = None

        if thesis and _needs_daily_thesis_assessment(pos, thesis, thesis_status):
            try:
                technicals = await get_technicals(redis, ticker)
                assessment = await _assess_thesis_daily(
                    pos=pos,
                    thesis=thesis,
                    technicals=technicals,
                    market_context=market_context,
                )
                thesis_status = _apply_thesis_assessment(db, thesis, assessment)

                assessment_flag = _flag_from_assessment(pos, thesis_status, thesis, assessment)
                if assessment_flag:
                    flags.append(assessment_flag)
            except Exception as exc:
                logger.warning("Daily thesis assessment failed for %s: %s", ticker, exc)

        # --- ZOMBIE DETECTION ---
        is_zombie = _check_zombie(thesis, thesis_status)
        if is_zombie and not _has_flag(flags, ticker, "zombie"):
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="zombie",
                detail="Pozice bez aktivní teze — zvažit exit při příležitosti.",
                urgency="high",
            ))

        if thesis_status == "delivered" and not _has_flag(flags, ticker, "thesis_delivered"):
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="thesis_delivered",
                detail=_join_parts(
                    "Teze je označená jako delivered — zvaž realizaci zisku nebo rotaci kapitálu.",
                    _strategy_tail(thesis, "profit_taking_plan", prefix="Původní plán zisků: "),
                ),
            ))

        # --- ADD TRIGGER (Type A/B only) ---
        if pos.play_type != "C" and thesis_status in ("intact",):
            if pos.unrealized_pnl_pct <= -20 and not _has_flag(flags, ticker, "add_trigger"):
                flags.append(PositionFlag(
                    ticker=ticker,
                    flag_type="add_trigger",
                    detail=f"Pokles {pos.unrealized_pnl_pct:.1f}% — thesis intact, zvažit přikoupení.",
                ))

        # --- TYPE B CATALYST PLAYED OUT / DELIVERED HEURISTIC ---
        if pos.play_type == "B" and thesis_status == "intact" and pos.unrealized_pnl_pct >= 18:
            try:
                technicals = technicals or await get_technicals(redis, ticker)
                rsi14 = technicals.get("rsi14")
                if rsi14 and rsi14 >= 68 and not _has_flag(flags, ticker, "thesis_delivered"):
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="thesis_delivered",
                        detail=_join_parts(
                            f"Type B pozice +{pos.unrealized_pnl_pct:.1f}% a RSI {rsi14:.1f} — catalyst může být z velké části odehraný, zvaž staged exit nebo rotaci.",
                            _strategy_tail(thesis, "profit_taking_plan", prefix="Původní plán zisků: "),
                        ),
                    ))
            except Exception:
                pass

        # --- TYPE C EXIT TRIGGER ---
        if pos.play_type == "C" and pos.change_pct is not None:
            if pos.change_pct <= -5 and not _has_flag(flags, ticker, "exit_now"):
                flags.append(PositionFlag(
                    ticker=ticker,
                    flag_type="exit_now",
                    detail=_join_parts(
                        f"Type C pozice −{abs(pos.change_pct):.1f}% za den — exit pravidlo aktivováno.",
                        _strategy_tail(thesis, "invalidation_conditions", prefix="Původní invalidace: "),
                    ),
                    urgency="high",
                ))

        # --- TYPE C PROFIT-TAKING ---
        if pos.play_type == "C" and pos.unrealized_pnl_pct >= 12:
            try:
                technicals = technicals or await get_technicals(redis, ticker)
                rsi14 = technicals.get("rsi14")
                if rsi14 and rsi14 >= 70 and not _has_flag(flags, ticker, "partial_profit"):
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="partial_profit",
                        detail=_join_parts(
                            f"Type C pozice +{pos.unrealized_pnl_pct:.1f}% a RSI {rsi14:.1f} — zvaž staged výběr zisku.",
                            _strategy_tail(thesis, "profit_taking_plan", prefix="Původní plán zisků: "),
                        ),
                    ))
            except Exception:
                pass

        # --- SENTIMENT SPIKE TACTICAL SIGNAL ---
        if pos.play_type in ("A", "B") and market_context.fng_spike and pos.unrealized_pnl_pct >= 15 and not _has_flag(flags, ticker, "partial_profit"):
            flags.append(PositionFlag(
                ticker=ticker,
                flag_type="partial_profit",
                detail=_join_parts(
                    f"Sentiment spike detekován — pozice +{pos.unrealized_pnl_pct:.1f}%, zvaž parciální výběr zisku.",
                    _strategy_tail(thesis, "profit_taking_plan", prefix="Původní plán zisků: "),
                ),
            ))

        # --- NEWS ALERT (only for flagged positions) ---
        if (is_zombie or thesis_status in ("weakening",)) and not _has_flag(flags, ticker, "news_alert"):
            try:
                news = await search(f"{ticker} stock news latest", max_results=2, days=7)
                if news:
                    snippet = news[0].get("title", "")[:100]
                    flags.append(PositionFlag(
                        ticker=ticker,
                        flag_type="news_alert",
                        detail=_join_parts(
                            f"Poslední zprávy: {snippet}",
                            _strategy_tail(thesis, "monitoring_focus", prefix="Co jsi chtěl hlídat: "),
                        ),
                    ))
            except Exception:
                pass

    return flags


async def _assess_thesis_daily(
    *,
    pos: PositionSnapshot,
    thesis: dict,
    technicals: dict,
    market_context: MarketContext,
) -> dict:
    try:
        news_results = await search(f"{pos.ticker} stock latest earnings guidance analyst news", max_results=3, days=7)
        news_context = format_results(news_results)
    except Exception:
        news_context = "Zadne vysledky nenalezeny."

    user_prompt = f"""Ticker: {pos.ticker}
Play type: {pos.play_type}
Current price: {pos.current_price}
Avg cost: {pos.avg_cost}
Daily change pct: {pos.change_pct}
Unrealized P/L pct: {pos.unrealized_pnl_pct}
Market regime: {market_context.market_regime}, F&G: {market_context.fng_score}

Stored thesis:
Status: {thesis.get('status')}
Entry thesis: {thesis.get('entry_thesis')}
Entry rationale: {thesis.get('entry_rationale')}
Invalidation conditions: {thesis.get('invalidation_conditions')}
Profit-taking plan: {thesis.get('profit_taking_plan')}
Monitoring focus: {thesis.get('monitoring_focus')}
Horizon: {thesis.get('holding_horizon')}

Technicals:
RSI14: {technicals.get('rsi14')}
Trend: {technicals.get('trend_signal')}
SMA50: {technicals.get('sma50')}
SMA200: {technicals.get('sma200')}

Fresh context:
{news_context[:1200]}"""

    response = await call_llm(THESIS_CHECK_PROMPT, user_prompt, max_tokens=260, label=f'daily_thesis_check:{pos.ticker}')
    parsed = _parse_json_object(response)
    if not parsed:
        return {
            "status": thesis.get("status", "intact"),
            "action_bias": "watch",
            "urgency": "normal",
            "summary": "Denní thesis check nebylo možné spolehlivě parsovat.",
        }
    return parsed


def _apply_thesis_assessment(db, thesis: dict, assessment: dict) -> str:
    old_status = thesis.get("status", "intact")
    new_status = assessment.get("status") or old_status
    valid_statuses = {"intact", "weakening", "zombie", "invalidated", "delivered"}
    if new_status not in valid_statuses:
        new_status = old_status

    summary = assessment.get("summary") or "Denní thesis check."
    action_bias = assessment.get("action_bias")
    urgency = assessment.get("urgency", "normal")

    now = datetime.now(timezone.utc).isoformat()

    # Always update last_check fields; update status only if changed or action is notable
    update_payload: dict = {
        "last_thesis_check_at": now,
        "last_thesis_check_summary": summary,
        "last_thesis_check_action_bias": action_bias,
        "last_thesis_check_urgency": urgency,
        "updated_at": now,
    }
    if new_status != old_status:
        update_payload["status"] = new_status

    db.table("theses").update(update_payload).eq("id", thesis["id"]).execute()

    # Insert event only when status changed or action is notable
    if new_status != old_status or action_bias not in (None, "hold", "watch"):
        thesis_with_id = {**thesis}
        create_thesis_event(
            db,
            thesis=thesis_with_id,
            kind="daily_check",
            text=summary,
            payload={
                "action_bias": action_bias,
                "urgency": urgency,
            },
            status_before=old_status,
            status_after=new_status,
        )

    return new_status


def _flag_from_assessment(pos: PositionSnapshot, thesis_status: str, thesis: dict, assessment: dict) -> Optional[PositionFlag]:
    action_bias = assessment.get("action_bias")
    urgency = assessment.get("urgency") or "normal"
    summary = assessment.get("summary") or "Denní thesis check signalizuje změnu."

    if thesis_status == "invalidated" or action_bias == "exit_now":
        return PositionFlag(
            ticker=pos.ticker,
            flag_type="exit_now",
            detail=_join_parts(
                summary,
                _strategy_tail(thesis, "invalidation_conditions", prefix="Původní invalidace: "),
            ),
            urgency="high",
        )

    if thesis_status == "delivered" or action_bias == "reduce_or_take_profit":
        return PositionFlag(
            ticker=pos.ticker,
            flag_type="thesis_delivered",
            detail=_join_parts(
                summary,
                _strategy_tail(thesis, "profit_taking_plan", prefix="Původní plán zisků: "),
            ),
            urgency=urgency,
        )

    if action_bias == "add_candidate" and pos.play_type != "C" and pos.unrealized_pnl_pct <= -10:
        return PositionFlag(
            ticker=pos.ticker,
            flag_type="add_trigger",
            detail=_join_parts(
                summary,
                f"Pozice je {pos.unrealized_pnl_pct:.1f}% pod vstupem.",
            ),
            urgency=urgency,
        )

    if thesis_status == "weakening":
        return PositionFlag(
            ticker=pos.ticker,
            flag_type="news_alert",
            detail=_join_parts(
                summary,
                _strategy_tail(thesis, "monitoring_focus", prefix="Co hlídat: "),
            ),
            urgency=urgency,
        )

    return None


def _check_zombie(thesis: Optional[dict], thesis_status: str) -> bool:
    if thesis_status == "zombie":
        return True
    if not thesis:
        return False
    # Staleness: use last_thesis_check_at, fall back to updated_at
    ts_str = thesis.get("last_thesis_check_at") or thesis.get("updated_at")
    if ts_str:
        try:
            last_update = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last_update) > timedelta(days=60):
                return True
        except Exception:
            pass
    return False


def _needs_daily_thesis_assessment(pos: PositionSnapshot, thesis: dict, thesis_status: str) -> bool:
    if thesis_status in {"weakening", "invalidated", "delivered", "zombie"}:
        return True

    if pos.change_pct is not None and abs(pos.change_pct) >= 4:
        return True

    if pos.unrealized_pnl_pct <= -10 or pos.unrealized_pnl_pct >= 12:
        return True

    # No strategy fields yet — needs first check
    has_strategy = any(thesis.get(f) for f in ("invalidation_conditions", "profit_taking_plan", "monitoring_focus"))
    if not has_strategy:
        return True

    last_check_str = thesis.get("last_thesis_check_at")
    if not last_check_str:
        return True

    try:
        last_check = datetime.fromisoformat(str(last_check_str).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last_check) > timedelta(days=7)
    except Exception:
        return True


def _strategy_tail(thesis: Optional[dict], field: str, *, prefix: str) -> Optional[str]:
    if not thesis:
        return None
    value = thesis.get(field)
    if not value:
        return None
    compact = " ".join(str(value).split())
    if len(compact) > 180:
        compact = compact[:177].rstrip() + "..."
    return f"{prefix}{compact}"


def _join_parts(*parts: Optional[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _parse_json_object(text: str) -> Optional[dict]:
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


def _has_flag(flags: List[PositionFlag], ticker: str, flag_type: str) -> bool:
    return any(flag.ticker == ticker and flag.flag_type == flag_type for flag in flags)
