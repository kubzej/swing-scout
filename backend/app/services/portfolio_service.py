"""
Portfolio service — P&L calculation, cash balance, sector exposure, snapshot.

Theme/sector detection is fully dynamic via yfinance fundamentals (Redis cached 24h).
No hardcoded ticker lists.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from app.core.supabase import get_supabase
from app.services.market.quotes import get_quotes, get_fx_rates, to_czk
import logging

logger = logging.getLogger(__name__)


@dataclass
class PositionSnapshot:
    id: str
    ticker: str
    shares: float
    avg_cost: float
    currency: str
    play_type: str
    status: str
    current_price: Optional[float]
    yesterday_close: Optional[float]
    change_pct: Optional[float]
    current_value_czk: float
    cost_czk: float
    unrealized_pnl_czk: float
    unrealized_pnl_pct: float
    realized_pnl_czk: Optional[float]
    sector: Optional[str]   # from yfinance — used for concentration guard


@dataclass
class PortfolioSnapshot:
    total_value_czk: float
    total_cost_czk: float
    total_pnl_czk: float
    total_pnl_pct: float
    cash_czk: float
    starting_cash_czk: float
    total_return_pct: float
    total_realized_pnl_czk: float = 0.0
    positions: List[PositionSnapshot] = field(default_factory=list)
    sector_exposure: Dict[str, float] = field(default_factory=dict)


def get_settings(user_id: str) -> dict:
    db = get_supabase()
    response = db.table("settings").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0]
    defaults = {
        "user_id": user_id,
        "starting_cash_czk": 1000000,
        "max_positions": 20,
        "cash_reserve_pct": 0.07,
    }
    db.table("settings").insert(defaults).execute()
    return defaults


def _calc_sector_exposure(positions: List[PositionSnapshot], total_value: float) -> Dict[str, float]:
    if total_value <= 0:
        return {}
    exposure: Dict[str, float] = {}
    for pos in positions:
        if pos.sector and pos.current_value_czk > 0:
            exposure[pos.sector] = exposure.get(pos.sector, 0.0) + pos.current_value_czk
    return {sector: round(val / total_value * 100, 1) for sector, val in exposure.items()}


async def get_portfolio_snapshot(user_id: str, redis) -> PortfolioSnapshot:
    from app.services.market.financials import get_fundamentals

    db = get_supabase()
    settings = get_settings(user_id)
    starting_cash = float(settings.get("starting_cash_czk", 1000000))

    pos_response = (
        db.table("positions")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "open")
        .execute()
    )
    raw_positions = pos_response.data or []

    tx_response = (
        db.table("transactions")
        .select("size_czk, action, realized_pnl_czk")
        .eq("user_id", user_id)
        .execute()
    )
    cash_spent = 0.0
    total_realized_pnl_czk = 0.0
    for tx in (tx_response.data or []):
        size = float(tx.get("size_czk") or 0)
        if tx.get("action") == "buy":
            cash_spent += size
        elif tx.get("action") == "sell":
            cash_spent -= size
        total_realized_pnl_czk += float(tx.get("realized_pnl_czk") or 0)

    cash_czk = max(0.0, starting_cash - cash_spent)

    if not raw_positions:
        return PortfolioSnapshot(
            total_value_czk=cash_czk,
            total_cost_czk=0.0,
            total_pnl_czk=0.0,
            total_pnl_pct=0.0,
            cash_czk=cash_czk,
            starting_cash_czk=starting_cash,
            total_return_pct=round((cash_czk - starting_cash) / starting_cash * 100, 2),
            total_realized_pnl_czk=round(total_realized_pnl_czk, 2),
        )

    tickers = [p["ticker"] for p in raw_positions]
    quotes = await get_quotes(redis, tickers)
    fx = await get_fx_rates(redis)

    positions: List[PositionSnapshot] = []
    invested_value_czk = 0.0
    total_cost_czk = 0.0

    for p in raw_positions:
        ticker = p["ticker"]
        shares = float(p["shares"])
        avg_cost = float(p["avg_cost"])
        currency = p.get("currency", "USD")

        quote = quotes.get(ticker, {})
        current_price = quote.get("price")
        yesterday_close = quote.get("yesterday_close")
        change_pct = quote.get("change_pct")

        cost_czk = to_czk(shares * avg_cost, currency, fx)
        current_value_czk = to_czk(shares * current_price, currency, fx) if current_price else cost_czk
        pnl_czk = current_value_czk - cost_czk
        pnl_pct = round(pnl_czk / cost_czk * 100, 2) if cost_czk > 0 else 0.0

        invested_value_czk += current_value_czk
        total_cost_czk += cost_czk

        # Dynamic sector from yfinance (Redis cached 24h — no extra latency)
        sector = None
        try:
            fundamentals = await get_fundamentals(redis, ticker)
            sector = fundamentals.get("sector")
        except Exception:
            pass

        positions.append(PositionSnapshot(
            id=p["id"],
            ticker=ticker,
            shares=shares,
            avg_cost=avg_cost,
            currency=currency,
            play_type=p.get("play_type", "A"),
            status=p.get("status", "open"),
            current_price=current_price,
            yesterday_close=yesterday_close,
            change_pct=change_pct,
            current_value_czk=round(current_value_czk, 2),
            cost_czk=round(cost_czk, 2),
            unrealized_pnl_czk=round(pnl_czk, 2),
            unrealized_pnl_pct=pnl_pct,
            realized_pnl_czk=p.get("realized_pnl_czk"),
            sector=sector,
        ))

    total_portfolio_value = invested_value_czk + cash_czk
    total_pnl_czk = invested_value_czk - total_cost_czk
    total_pnl_pct = round(total_pnl_czk / total_cost_czk * 100, 2) if total_cost_czk > 0 else 0.0
    total_return_pct = round((total_portfolio_value - starting_cash) / starting_cash * 100, 2)

    sector_exposure = _calc_sector_exposure(positions, total_portfolio_value)

    return PortfolioSnapshot(
        total_value_czk=round(total_portfolio_value, 2),
        total_cost_czk=round(total_cost_czk, 2),
        total_pnl_czk=round(total_pnl_czk, 2),
        total_pnl_pct=total_pnl_pct,
        cash_czk=round(cash_czk, 2),
        starting_cash_czk=starting_cash,
        total_return_pct=total_return_pct,
        total_realized_pnl_czk=round(total_realized_pnl_czk, 2),
        positions=positions,
        sector_exposure=sector_exposure,
    )
