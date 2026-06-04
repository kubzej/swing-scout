from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ThesisCreate(BaseModel):
    position_id: Optional[str] = None
    ticker: str
    entry_thesis: str
    entry_rationale: Optional[str] = None
    invalidation_conditions: Optional[str] = None
    profit_taking_plan: Optional[str] = None
    monitoring_focus: Optional[str] = None
    holding_horizon: Optional[str] = None
    add_plan: Optional[str] = None
    exit_plan: Optional[str] = None
    play_type: str = "A"
    source_recommendation_id: Optional[str] = None


class ThesisUpdate(BaseModel):
    new_status: Optional[str] = None
    note: Optional[str] = None
    invalidation_conditions: Optional[str] = None
    profit_taking_plan: Optional[str] = None
    monitoring_focus: Optional[str] = None
    holding_horizon: Optional[str] = None
    add_plan: Optional[str] = None
    exit_plan: Optional[str] = None


class ThesisEventResponse(BaseModel):
    id: str
    thesis_id: str
    user_id: str
    position_id: Optional[str]
    ticker: str
    kind: str
    text: Optional[str]
    payload: Any
    status_before: Optional[str]
    status_after: Optional[str]
    created_at: datetime


class ThesisResponse(BaseModel):
    id: str
    position_id: Optional[str]
    user_id: str
    ticker: str
    play_type: str
    status: str
    entry_thesis: str
    entry_rationale: Optional[str]
    invalidation_conditions: Optional[str]
    profit_taking_plan: Optional[str]
    monitoring_focus: Optional[str]
    holding_horizon: Optional[str]
    add_plan: Optional[str]
    exit_plan: Optional[str]
    source_recommendation_id: Optional[str]
    last_thesis_check_at: Optional[datetime]
    last_thesis_check_summary: Optional[str]
    last_thesis_check_action_bias: Optional[str]
    last_thesis_check_urgency: Optional[str]
    created_at: datetime
    updated_at: datetime
    events: List[ThesisEventResponse] = []
