from datetime import datetime, timezone
from typing import Optional


def create_thesis_event(
    db,
    *,
    thesis: dict,
    kind: str,
    text: Optional[str] = None,
    payload: Optional[dict] = None,
    status_before: Optional[str] = None,
    status_after: Optional[str] = None,
) -> None:
    db.table("thesis_events").insert({
        "thesis_id": thesis["id"],
        "user_id": thesis["user_id"],
        "position_id": thesis.get("position_id"),
        "ticker": thesis["ticker"],
        "kind": kind,
        "text": text,
        "payload": payload or {},
        "status_before": status_before,
        "status_after": status_after,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def get_current_thesis(db, user_id: str, position_id: str) -> Optional[dict]:
    response = (
        db.table("theses")
        .select("*")
        .eq("user_id", user_id)
        .eq("position_id", position_id)
        .execute()
    )
    return response.data[0] if response.data else None
