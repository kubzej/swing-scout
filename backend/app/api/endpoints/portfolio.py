from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.schemas.positions import PositionCreate, PositionResponse
from app.services.portfolio_service import get_portfolio_snapshot
from typing import List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    status: str = "open",
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    response = (
        db.table("positions")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", status)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


@router.post("/positions", response_model=PositionResponse, status_code=201)
async def create_position(
    data: PositionCreate,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    payload = {
        "user_id": user_id,
        "ticker": data.ticker.upper(),
        "shares": data.shares,
        "avg_cost": data.avg_cost,
        "currency": data.currency,
        "play_type": data.play_type.value,
        "status": "open",
        "opened_at": (data.opened_at or datetime.now(timezone.utc)).isoformat(),
    }
    response = db.table("positions").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se vytvořit pozici")
    return response.data[0]


@router.get("/snapshot")
async def get_portfolio(user_id: str = Depends(get_current_user_id)):
    redis = get_redis()
    snapshot = await get_portfolio_snapshot(user_id, redis)
    return {
        "total_value_czk": snapshot.total_value_czk,
        "total_cost_czk": snapshot.total_cost_czk,
        "total_pnl_czk": snapshot.total_pnl_czk,
        "total_pnl_pct": snapshot.total_pnl_pct,
        "cash_czk": snapshot.cash_czk,
        "starting_cash_czk": snapshot.starting_cash_czk,
        "total_return_pct": snapshot.total_return_pct,
        "sector_exposure": snapshot.sector_exposure,
        "positions": [
            {
                "id": p.id,
                "ticker": p.ticker,
                "shares": p.shares,
                "avg_cost": p.avg_cost,
                "currency": p.currency,
                "play_type": p.play_type,
                "current_price": p.current_price,
                "change_pct": p.change_pct,
                "current_value_czk": p.current_value_czk,
                "cost_czk": p.cost_czk,
                "unrealized_pnl_czk": p.unrealized_pnl_czk,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "sector": p.sector,
            }
            for p in snapshot.positions
        ],
    }
