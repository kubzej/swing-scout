from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.schemas.theses import ThesisCreate, ThesisUpdate, ThesisResponse
from app.services.thesis_service import create_thesis_event, get_current_thesis
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ThesisResponse, status_code=201)
async def create_thesis(
    data: ThesisCreate,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    payload = {
        "user_id": user_id,
        "position_id": data.position_id,
        "ticker": data.ticker.upper(),
        "entry_thesis": data.entry_thesis,
        "entry_rationale": data.entry_rationale,
        "invalidation_conditions": data.invalidation_conditions,
        "profit_taking_plan": data.profit_taking_plan,
        "monitoring_focus": data.monitoring_focus,
        "holding_horizon": data.holding_horizon,
        "add_plan": data.add_plan,
        "exit_plan": data.exit_plan,
        "play_type": data.play_type,
        "source_recommendation_id": data.source_recommendation_id,
        "status": "intact",
    }
    response = db.table("theses").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se vytvořit thesis")
    thesis = response.data[0]
    thesis["events"] = []
    return thesis


@router.get("/{position_id}", response_model=ThesisResponse)
async def get_thesis(
    position_id: str,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    thesis = get_current_thesis(db, user_id, position_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis nenalezena")

    events_response = (
        db.table("thesis_events")
        .select("*")
        .eq("thesis_id", thesis["id"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    thesis["events"] = events_response.data or []
    return thesis


@router.patch("/{thesis_id}", response_model=ThesisResponse)
async def update_thesis(
    thesis_id: str,
    data: ThesisUpdate,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()

    existing = (
        db.table("theses")
        .select("*")
        .eq("id", thesis_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Thesis nenalezena")

    thesis = existing.data[0]
    old_status = thesis["status"]
    new_status = data.new_status or old_status

    update_payload: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.new_status:
        update_payload["status"] = new_status
    if data.invalidation_conditions is not None:
        update_payload["invalidation_conditions"] = data.invalidation_conditions
    if data.profit_taking_plan is not None:
        update_payload["profit_taking_plan"] = data.profit_taking_plan
    if data.monitoring_focus is not None:
        update_payload["monitoring_focus"] = data.monitoring_focus
    if data.holding_horizon is not None:
        update_payload["holding_horizon"] = data.holding_horizon
    if data.add_plan is not None:
        update_payload["add_plan"] = data.add_plan
    if data.exit_plan is not None:
        update_payload["exit_plan"] = data.exit_plan

    response = (
        db.table("theses")
        .update(update_payload)
        .eq("id", thesis_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se aktualizovat thesis")

    updated_thesis = response.data[0]

    create_thesis_event(
        db,
        thesis=updated_thesis,
        kind="manual_update",
        text=data.note or "Ruční aktualizace thesis.",
        payload={k: v for k, v in update_payload.items() if k != "updated_at"},
        status_before=old_status,
        status_after=new_status,
    )

    events_response = (
        db.table("thesis_events")
        .select("*")
        .eq("thesis_id", thesis_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    updated_thesis["events"] = events_response.data or []
    return updated_thesis
