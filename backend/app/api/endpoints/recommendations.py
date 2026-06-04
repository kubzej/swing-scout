from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.services.market.quotes import get_fx_rates, get_fx_rate
from app.services.thesis_service import create_thesis_event, get_current_thesis
from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _with_source_run_type(rows: list[dict] | None) -> list[dict]:
    enriched: list[dict] = []
    for row in rows or []:
        item = dict(row)
        item["source_run_type"] = "daily" if item.get("run_id") else "intraday"
        enriched.append(item)
    return enriched


class ConfirmRequest(BaseModel):
    actual_price: float
    actual_shares: Optional[int] = None

    @model_validator(mode="after")
    def validate_values(self):
        if self.actual_price <= 0:
            raise ValueError("actual_price musí být větší než 0")
        if self.actual_shares is not None and self.actual_shares <= 0:
            raise ValueError("actual_shares musí být větší než 0")
        return self


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/fx-rates")
async def fx_rates_endpoint(
    _user_id: str = Depends(get_current_user_id),
):
    redis = get_redis()
    fx = await get_fx_rates(redis)
    return {
        "USD_CZK": fx.get("USD_CZK", 23.0),
        "EUR_CZK": fx.get("EUR_CZK", 25.0),
        "GBP_CZK": fx.get("GBP_CZK", 29.0),
        "HKD_CZK": fx.get("HKD_CZK", 3.0),
        "CHF_CZK": fx.get("CHF_CZK", 26.5),
        "SEK_CZK": fx.get("SEK_CZK", 2.3),
        "PLN_CZK": fx.get("PLN_CZK", 5.9),
        "NOK_CZK": fx.get("NOK_CZK", 2.1),
        "DKK_CZK": fx.get("DKK_CZK", 3.35),
    }


@router.get("/")
async def list_recommendations(
    status: str = "pending",
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    query = (
        db.table("recommendations")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status != "all":
        statuses = [s.strip() for s in status.split(",")]
        if len(statuses) == 1:
            query = query.eq("status", statuses[0])
        else:
            query = query.in_("status", statuses)
    response = query.execute()
    return _with_source_run_type(response.data)


@router.post("/{rec_id}/confirm")
async def confirm_recommendation(
    rec_id: str,
    data: ConfirmRequest,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    redis = get_redis()

    rec = (
        db.table("recommendations")
        .select("*")
        .eq("id", rec_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not rec.data:
        raise HTTPException(status_code=404, detail="Doporučení nenalezeno")

    r = rec.data[0]
    if r["status"] not in ("pending", "updated"):
        raise HTTPException(status_code=400, detail="Doporučení již bylo zpracováno")

    action = r["action"]
    ticker = r["ticker"]
    from app.api.endpoints.transactions import _upsert_position

    if action in ("buy", "add", "sell", "exit"):
        fx = await get_fx_rates(redis)
        size_czk = r.get("recommended_size_czk") or 0

        pos_response = (
            db.table("positions")
            .select("shares, currency")
            .eq("user_id", user_id)
            .eq("ticker", ticker)
            .eq("status", "open")
            .execute()
        )
        pos_data = pos_response.data[0] if pos_response.data else None
        rec_opts = r.get("options_details") or {}
        currency = (pos_data.get("currency") if pos_data else None) or rec_opts.get("currency") or "USD"
        fx_rate = get_fx_rate(currency, fx)

        tx_action = "buy" if action in ("buy", "add") else "sell"

        if tx_action == "buy":
            shares = float(data.actual_shares) if data.actual_shares else round(size_czk / (data.actual_price * fx_rate), 4)
        elif action == "exit":
            shares = float(pos_data["shares"]) if pos_data else 0
        else:
            shares = float(data.actual_shares) if data.actual_shares else round(size_czk / (data.actual_price * fx_rate), 4)

        if shares <= 0:
            raise HTTPException(status_code=400, detail="Nelze vytvořit transakci s 0 akciemi")

        actual_size_czk = round(shares * data.actual_price * fx_rate, 2)

        try:
            realized_pnl_czk = await _upsert_position(
                db, user_id, ticker, tx_action,
                shares, data.actual_price, currency,
                r.get("play_type", "A"), rec_id, fx_rate
            )
        except Exception as e:
            logger.error("Position upsert failed for rec %s: %s", rec_id, e)
            raise HTTPException(status_code=500, detail="Nepodařilo se aktualizovat pozici")

        try:
            db.table("transactions").insert({
                "user_id": user_id,
                "ticker": ticker,
                "action": tx_action,
                "shares": shares,
                "price_per_share": data.actual_price,
                "currency": currency,
                "size_czk": actual_size_czk,
                "realized_pnl_czk": realized_pnl_czk if tx_action == "sell" else None,
                "recommendation_id": rec_id,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.error("Transaction insert failed for rec %s: %s", rec_id, e)
            raise HTTPException(status_code=500, detail="Nepodařilo se vytvořit transakci")

        # --- Thesis v2 write ---
        if action in ("buy", "add") and r.get("thesis_text"):
            try:
                pos_after = (
                    db.table("positions").select("id")
                    .eq("user_id", user_id).eq("ticker", ticker).eq("status", "open")
                    .execute()
                )
                if pos_after.data:
                    position_id = pos_after.data[0]["id"]
                    existing_thesis = get_current_thesis(db, user_id, position_id)

                    if not existing_thesis:
                        # New position — create thesis with first-class fields
                        thesis_payload = {
                            "user_id": user_id,
                            "position_id": position_id,
                            "ticker": ticker,
                            "entry_thesis": r["thesis_text"],
                            "entry_rationale": rec_opts.get("entry_rationale"),
                            "invalidation_conditions": rec_opts.get("invalidation_conditions"),
                            "profit_taking_plan": rec_opts.get("profit_taking_plan"),
                            "monitoring_focus": rec_opts.get("monitoring_focus"),
                            "holding_horizon": rec_opts.get("holding_horizon"),
                            "add_plan": _build_add_plan(r),
                            "exit_plan": rec_opts.get("exit_plan"),
                            "play_type": r.get("play_type", "A"),
                            "source_recommendation_id": rec_id,
                            "status": "intact",
                        }
                        thesis_response = db.table("theses").insert(thesis_payload).execute()
                        if thesis_response.data:
                            new_thesis = thesis_response.data[0]
                            create_thesis_event(
                                db,
                                thesis=new_thesis,
                                kind="opened",
                                text=f"Pozice otevřena: {r['thesis_text'][:300]}",
                                payload={
                                    "recommendation_id": rec_id,
                                    "action": action,
                                    "price": data.actual_price,
                                    "shares": shares,
                                    "size_czk": actual_size_czk,
                                    "currency": currency,
                                    "source": "daily" if r.get("run_id") else "intraday",
                                },
                                status_before=None,
                                status_after="intact",
                            )
                    else:
                        # Existing position — update strategy fields if recommendation has newer values
                        update_fields: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
                        for field in ("invalidation_conditions", "profit_taking_plan", "monitoring_focus", "holding_horizon"):
                            new_val = rec_opts.get(field)
                            if new_val and new_val.strip():
                                update_fields[field] = new_val
                        if len(update_fields) > 1:
                            db.table("theses").update(update_fields).eq("id", existing_thesis["id"]).execute()
                            existing_thesis.update(update_fields)

                        create_thesis_event(
                            db,
                            thesis=existing_thesis,
                            kind="scaled",
                            text=f"Přikoupení potvrzeno: {r.get('thesis_text', '')[:300]}",
                            payload={
                                "recommendation_id": rec_id,
                                "action": action,
                                "price": data.actual_price,
                                "shares": shares,
                                "size_czk": actual_size_czk,
                                "currency": currency,
                                "source": "daily" if r.get("run_id") else "intraday",
                                "strategy_at_add": {
                                    "invalidation_conditions": rec_opts.get("invalidation_conditions"),
                                    "profit_taking_plan": rec_opts.get("profit_taking_plan"),
                                    "holding_horizon": rec_opts.get("holding_horizon"),
                                    "monitoring_focus": rec_opts.get("monitoring_focus"),
                                    "entry_rationale": rec_opts.get("entry_rationale"),
                                },
                            },
                            status_before=existing_thesis.get("status", "intact"),
                            status_after=existing_thesis.get("status", "intact"),
                        )
            except Exception as e:
                logger.warning("Thesis create/update failed for %s: %s", ticker, e)

        elif action in ("sell", "exit"):
            try:
                # Find thesis for current (or just-closed) position
                pos_for_thesis = (
                    db.table("positions").select("id, status")
                    .eq("user_id", user_id).eq("ticker", ticker)
                    .order("created_at", desc=True).limit(1)
                    .execute()
                )
                if pos_for_thesis.data:
                    position_id = pos_for_thesis.data[0]["id"]
                    thesis = get_current_thesis(db, user_id, position_id)
                    if not thesis:
                        # Try without user_id filter (position might be closed)
                        thesis_resp = (
                            db.table("theses").select("*")
                            .eq("position_id", position_id).eq("user_id", user_id)
                            .execute()
                        )
                        thesis = thesis_resp.data[0] if thesis_resp.data else None

                    if thesis:
                        pos_after = (
                            db.table("positions").select("status")
                            .eq("id", position_id).execute()
                        )
                        is_closed = (
                            not pos_after.data or
                            pos_after.data[0].get("status") == "closed" or
                            action == "exit"
                        )
                        create_thesis_event(
                            db,
                            thesis=thesis,
                            kind="closed" if is_closed else "partial_exit",
                            text=f"{'Pozice uzavřena' if is_closed else 'Částečný výstup'}: {r.get('thesis_text', '')[:200]}",
                            payload={
                                "recommendation_id": rec_id,
                                "action": action,
                                "price": data.actual_price,
                                "shares": shares,
                                "size_czk": actual_size_czk,
                                "currency": currency,
                                "realized_pnl_czk": realized_pnl_czk,
                            },
                            status_before=thesis.get("status", "intact"),
                            status_after=thesis.get("status", "intact"),
                        )
            except Exception as e:
                logger.warning("Thesis exit event failed for %s: %s", ticker, e)

    db.table("recommendations").update({
        "status": "confirmed",
        "actual_price": data.actual_price,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rec_id).execute()

    if action in ("buy", "add"):
        try:
            from app.agent.watchlist_manager import remove_from_watchlist
            await remove_from_watchlist(user_id, ticker)
        except Exception as e:
            logger.warning("Watchlist cleanup failed for %s: %s", ticker, e)

    return {"status": "confirmed", "rec_id": rec_id}


def _build_add_plan(rec: dict) -> Optional[str]:
    reserve = rec.get("add_reserve_czk")
    if reserve and float(reserve) > 0:
        return f"Rezerva na přikoupení: {int(reserve):,} CZK"
    return None


@router.post("/{rec_id}/reject")
async def reject_recommendation(
    rec_id: str,
    data: RejectRequest,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()

    rec = (
        db.table("recommendations")
        .select("id, status, ticker, action")
        .eq("id", rec_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not rec.data:
        raise HTTPException(status_code=404, detail="Doporučení nenalezeno")
    if rec.data[0]["status"] not in ("pending", "updated"):
        raise HTTPException(status_code=400, detail="Doporučení již bylo zpracováno")

    ticker = rec.data[0].get("ticker", "")
    action = rec.data[0].get("action", "")

    db.table("recommendations").update({
        "status": "rejected",
        "rejection_reason": data.reason,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rec_id).execute()

    # Rejecting a sell/exit/add on a held position is a thesis-level decision.
    # Record it as an audit event; for exits, also set an override that mutes routine
    # exit/reduce flags for a few days so the agent doesn't re-flag the same exit.
    if ticker and action in ("sell", "exit", "add"):
        try:
            pos = (
                db.table("positions").select("id")
                .eq("user_id", user_id).eq("ticker", ticker).eq("status", "open")
                .execute()
            )
            if pos.data:
                thesis = get_current_thesis(db, user_id, pos.data[0]["id"])
                if thesis:
                    is_exit_reject = action in ("sell", "exit")
                    reason_text = data.reason or ("Uživatel odmítl výstup." if is_exit_reject else "Uživatel odmítl přikoupení.")
                    create_thesis_event(
                        db,
                        thesis=thesis,
                        kind="rejected_exit" if is_exit_reject else "rejected_add",
                        text=reason_text,
                        payload={"recommendation_id": rec_id, "action": action},
                        status_before=thesis.get("status", "intact"),
                        status_after=thesis.get("status", "intact"),
                    )
                    if is_exit_reject:
                        db.table("theses").update({
                            "last_user_override_at": datetime.now(timezone.utc).isoformat(),
                            "last_user_override_summary": reason_text,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }).eq("id", thesis["id"]).execute()
        except Exception as e:
            logger.warning("Thesis override/reject event failed for %s: %s", ticker, e)

    if ticker:
        try:
            from app.agent.watchlist_manager import remove_from_watchlist
            await remove_from_watchlist(user_id, ticker)
        except Exception as e:
            logger.warning("Watchlist cleanup failed for %s: %s", ticker, e)

    return {"status": "rejected", "rec_id": rec_id}


@router.get("/history")
async def recommendation_history(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    response = (
        db.table("recommendations")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _with_source_run_type(response.data)
