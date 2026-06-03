from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.schemas.theses import ThesisCreate, ThesisNoteAppend, ThesisResponse
from datetime import datetime, timezone
import json
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
        "exit_conditions": data.exit_conditions,
        "horizon": data.horizon,
        "play_type": data.play_type,
        "status": "intact",
        "notes_log": [],
    }
    response = db.table("theses").insert(payload).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se vytvořit thesis")
    return response.data[0]


@router.get("/{position_id}", response_model=ThesisResponse)
async def get_thesis(
    position_id: str,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    response = (
        db.table("theses")
        .select("*")
        .eq("user_id", user_id)
        .eq("position_id", position_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Thesis nenalezena")
    return response.data[0]


@router.patch("/{thesis_id}", response_model=ThesisResponse)
async def update_thesis(
    thesis_id: str,
    data: ThesisNoteAppend,
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
    current_status = thesis["status"]
    new_status = data.new_status or current_status

    notes_log = thesis.get("notes_log") or []
    notes_log.append({
        "text": data.note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status_before": current_status,
        "status_after": new_status,
    })

    update_payload = {
        "status": new_status,
        "notes_log": json.dumps(notes_log),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    response = (
        db.table("theses")
        .update(update_payload)
        .eq("id", thesis_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=500, detail="Nepodařilo se aktualizovat thesis")
    return response.data[0]
