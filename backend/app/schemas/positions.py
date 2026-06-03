from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class PlayType(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class PositionStatus(str, Enum):
    open = "open"
    closed = "closed"


class PositionCreate(BaseModel):
    ticker: str
    shares: float
    avg_cost: float
    currency: str = "USD"
    play_type: PlayType
    opened_at: Optional[datetime] = None


class PositionResponse(BaseModel):
    id: str
    user_id: str
    ticker: str
    shares: float
    avg_cost: float
    currency: str
    play_type: PlayType
    status: PositionStatus
    opened_at: datetime
    closed_at: Optional[datetime]
    created_at: datetime
