from fastapi import APIRouter, Depends
from app.core.auth import get_current_user_id
from app.agent.watchlist_manager import get_active_watchlist

router = APIRouter()


@router.get("/")
async def get_watchlist(user_id: str = Depends(get_current_user_id)):
    return await get_active_watchlist(user_id)
