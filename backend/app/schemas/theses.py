from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ThesisCreate(BaseModel):
    position_id: Optional[str] = None
    ticker: str
    entry_thesis: str
    exit_conditions: Optional[str] = None
    horizon: Optional[str] = None
    play_type: str = "A"


class ThesisNoteAppend(BaseModel):
    note: str
    new_status: Optional[str] = None


class ThesisResponse(BaseModel):
    id: str
    position_id: Optional[str]
    user_id: str
    ticker: str
    entry_thesis: str
    exit_conditions: Optional[str]
    horizon: Optional[str]
    play_type: str
    status: str
    notes_log: List[Any]
    created_at: datetime
    updated_at: datetime
