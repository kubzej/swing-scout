from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.schemas.transactions import TransactionCreate, TransactionResponse
from app.services.market.quotes import get_fx_rates, get_fx_rate, to_czk
from typing import List
from datetime import timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


async def _upsert_position(db, user_id: str, ticker: str, action: str,
                            shares: float, price: float, currency: str,
                            play_type: str = "A", recommendation_id: str = None,
                            fx_rate: float = 1.0) -> float:
    """Returns realized_pnl_czk for sell actions, 0.0 otherwise."""
    existing = (
        db.table("positions")
        .select("*")
        .eq("user_id", user_id)
        .eq("ticker", ticker)
        .eq("status", "open")
        .execute()
    )
    pos = existing.data[0] if existing.data else None

    if action == "buy":
        if pos:
            old_shares = float(pos["shares"])
            old_cost = float(pos["avg_cost"])
            new_shares = old_shares + shares
            new_avg_cost = (old_shares * old_cost + shares * price) / new_shares
            db.table("positions").update({
                "shares": round(new_shares, 6),
                "avg_cost": round(new_avg_cost, 6),
            }).eq("id", pos["id"]).execute()
        else:
            db.table("positions").insert({
                "user_id": user_id,
                "ticker": ticker.upper(),
                "shares": round(shares, 6),
                "avg_cost": round(price, 6),
                "currency": currency,
                "play_type": play_type,
                "status": "open",
                "realized_pnl_czk": 0,
            }).execute()
        return 0.0

    elif action == "sell":
        if not pos:
            raise HTTPException(status_code=400, detail=f"Nemáš otevřenou pozici {ticker}")
        remaining = float(pos["shares"]) - shares
        if remaining < -0.001:
            raise HTTPException(status_code=400, detail="Prodáváš víc akcií než vlastníš")

        avg_cost = float(pos.get("avg_cost") or 0)
        realized_pnl_local = (price - avg_cost) * shares
        realized_pnl_czk = round(realized_pnl_local * fx_rate, 2)
        prev_realized = float(pos.get("realized_pnl_czk") or 0)

        from datetime import datetime
        if remaining <= 0.001:
            db.table("positions").update({
                "shares": 0,
                "status": "closed",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "realized_pnl_czk": round(prev_realized + realized_pnl_czk, 2),
            }).eq("id", pos["id"]).execute()
        else:
            db.table("positions").update({
                "shares": round(remaining, 6),
                "realized_pnl_czk": round(prev_realized + realized_pnl_czk, 2),
            }).eq("id", pos["id"]).execute()

        return realized_pnl_czk

    return 0.0


@router.post("/", response_model=TransactionResponse, status_code=201)
async def log_transaction(
    data: TransactionCreate,
    user_id: str = Depends(get_current_user_id),
):
    if data.action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="action musí být 'buy' nebo 'sell'")

    db = get_supabase()
    redis = get_redis()

    fx = await get_fx_rates(redis)
    fx_rate = get_fx_rate(data.currency, fx)
    size_czk = to_czk(data.shares * data.price_per_share, data.currency, fx)

    # Determine play_type from recommendation if linked
    play_type = "A"
    if data.recommendation_id:
        rec = db.table("recommendations").select("play_type").eq("id", data.recommendation_id).eq("user_id", user_id).execute()
        if rec.data:
            play_type = rec.data[0].get("play_type", "A")

    realized_pnl_czk = await _upsert_position(
        db, user_id, data.ticker.upper(), data.action,
        data.shares, data.price_per_share, data.currency,
        play_type, data.recommendation_id, fx_rate
    )

    tx_payload = {
        "user_id": user_id,
        "ticker": data.ticker.upper(),
        "action": data.action,
        "shares": data.shares,
        "price_per_share": data.price_per_share,
        "currency": data.currency,
        "size_czk": round(size_czk, 2),
        "realized_pnl_czk": realized_pnl_czk if data.action == "sell" else None,
        "recommendation_id": data.recommendation_id,
        "executed_at": data.executed_at.isoformat(),
        "notes": data.notes,
    }
    response = db.table("transactions").insert(tx_payload).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se uložit transakci")
    return response.data[0]


class ManualTransactionCreate(TransactionCreate):
    play_type: str = "A"


@router.post("/manual", response_model=TransactionResponse, status_code=201)
async def log_manual_transaction(
    data: ManualTransactionCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Log a trade that was NOT based on an agent recommendation. Generates retroactive thesis."""
    if data.action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="action musí být 'buy' nebo 'sell'")

    db = get_supabase()
    redis = get_redis()

    fx = await get_fx_rates(redis)
    fx_rate = get_fx_rate(data.currency, fx)
    size_czk = to_czk(data.shares * data.price_per_share, data.currency, fx)

    realized_pnl_czk = await _upsert_position(
        db, user_id, data.ticker.upper(), data.action,
        data.shares, data.price_per_share, data.currency,
        data.play_type, None, fx_rate
    )

    tx_payload = {
        "user_id": user_id,
        "ticker": data.ticker.upper(),
        "action": data.action,
        "shares": data.shares,
        "price_per_share": data.price_per_share,
        "currency": data.currency,
        "size_czk": round(size_czk, 2),
        "realized_pnl_czk": realized_pnl_czk if data.action == "sell" else None,
        "recommendation_id": None,
        "executed_at": data.executed_at.isoformat(),
        "notes": data.notes,
    }
    tx_response = db.table("transactions").insert(tx_payload).execute()
    if not tx_response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se uložit transakci")

    # Generate retroactive thesis if this is a buy
    if data.action == "buy":
        try:
            from app.agent.thesis_generator import generate_retroactive_thesis
            thesis_data = await generate_retroactive_thesis(
                ticker=data.ticker.upper(),
                action=data.action,
                price=data.price_per_share,
                play_type=data.play_type,
            )
            pos_response = (
                db.table("positions")
                .select("id")
                .eq("user_id", user_id)
                .eq("ticker", data.ticker.upper())
                .eq("status", "open")
                .execute()
            )
            if pos_response.data:
                position_id = pos_response.data[0]["id"]
                db.table("theses").insert({
                    "user_id": user_id,
                    "position_id": position_id,
                    "ticker": data.ticker.upper(),
                    **thesis_data,
                    "notes_log": [],
                }).execute()
        except Exception as e:
            logger.warning("Retroactive thesis generation failed for %s: %s", data.ticker, e)

    return tx_response.data[0]


@router.get("/", response_model=List[TransactionResponse])
async def get_transactions(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    response = (
        db.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("executed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []
