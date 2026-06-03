from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TransactionCreate(BaseModel):
    ticker: str
    action: str  # buy | sell
    shares: float
    price_per_share: float
    currency: str = "USD"
    executed_at: datetime
    recommendation_id: Optional[str] = None
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    ticker: str
    action: str
    shares: float
    price_per_share: float
    currency: str
    size_czk: Optional[float]
    recommendation_id: Optional[str]
    executed_at: datetime
    notes: Optional[str]
    created_at: datetime
