from datetime import datetime, timezone, timedelta
from typing import Optional

# How long a user override (rejecting an exit/reduce on a held position) mutes
# routine exit/reduce flags for that position. A materially new high-urgency signal
# still gets through.
OVERRIDE_ACTIVE_DAYS = 7


def is_override_active(thesis: Optional[dict]) -> bool:
    if not thesis:
        return False
    ts = thesis.get("last_user_override_at")
    if not ts:
        return False
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - when) <= timedelta(days=OVERRIDE_ACTIVE_DAYS)


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


def get_add_context(db, user_id: str, position_id: str) -> dict:
    """For an add to a held position: thesis snapshot, entry confidence, tranches bought.

    confidence comes from the opening recommendation (thesis.source_recommendation_id);
    tranche_count is the number of opened/scaled/manual_scaled events on the thesis.
    Shared by the daily recommendation engine and the intraday run so both size adds
    and enforce the per-name tranche/concentration caps identically.
    """
    snapshot: Optional[dict] = None
    confidence = 3
    tranche_count = 0
    try:
        resp = (
            db.table("theses")
            .select("id, source_recommendation_id, invalidation_conditions, profit_taking_plan, monitoring_focus, holding_horizon, entry_thesis, status")
            .eq("user_id", user_id)
            .eq("position_id", position_id)
            .execute()
        )
        if resp.data:
            thesis = resp.data[0]
            snapshot = {
                k: thesis.get(k)
                for k in ("invalidation_conditions", "profit_taking_plan", "monitoring_focus", "holding_horizon", "entry_thesis", "status")
            }
            src_rec_id = thesis.get("source_recommendation_id")
            if src_rec_id:
                rec = db.table("recommendations").select("confidence").eq("id", src_rec_id).eq("user_id", user_id).execute()
                if rec.data and rec.data[0].get("confidence"):
                    confidence = int(rec.data[0]["confidence"])
            ev = (
                db.table("thesis_events")
                .select("kind")
                .eq("thesis_id", thesis["id"])
                .in_("kind", ["opened", "scaled", "manual_scaled"])
                .execute()
            )
            tranche_count = len(ev.data or [])
    except Exception:
        pass
    return {"thesis_snapshot": snapshot, "confidence": confidence, "tranche_count": tranche_count}
