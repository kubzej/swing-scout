from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.core.redis import get_redis
from app.services.market.quotes import get_fx_rates, get_fx_rate, to_czk
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


def _build_strategy_snapshot_note(*, invalidation: Optional[str], profit_plan: Optional[str], horizon: Optional[str], monitoring_focus: Optional[str], source_run_type: str) -> dict:
    return {
        "kind": "strategy_snapshot",
        "text": "Strategie při otevření pozice uložena.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status_before": None,
        "status_after": "intact",
        "strategy": {
            "invalidation_conditions": invalidation,
            "profit_taking_plan": profit_plan,
            "holding_horizon": horizon,
            "monitoring_focus": monitoring_focus,
            "source_run_type": source_run_type,
        },
    }


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
        # Support comma-separated statuses: "pending,updated"
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

    # --- Execute trade first, mark confirmed only on success ---
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

        # Create thesis on new buy
        if action in ("buy", "add") and r.get("thesis_text"):
            try:
                pos_after = (
                    db.table("positions").select("id")
                    .eq("user_id", user_id).eq("ticker", ticker).eq("status", "open")
                    .execute()
                )
                if pos_after.data:
                    position_id = pos_after.data[0]["id"]
                    existing = db.table("theses").select("id").eq("position_id", position_id).eq("user_id", user_id).execute()
                    if not existing.data:
                        invalidation = rec_opts.get("invalidation_conditions")
                        profit_plan = rec_opts.get("profit_taking_plan")
                        monitoring_focus = rec_opts.get("monitoring_focus")
                        horizon = rec_opts.get("holding_horizon")
                        combined_exit = "\n".join(
                            part for part in [
                                f"Invalidační podmínky: {invalidation}" if invalidation else None,
                                f"Výběr zisků: {profit_plan}" if profit_plan else None,
                                f"Monitoring: {monitoring_focus}" if monitoring_focus else None,
                            ] if part
                        ) or r.get("exit_conditions")
                        notes_log = [
                            _build_strategy_snapshot_note(
                                invalidation=invalidation,
                                profit_plan=profit_plan,
                                horizon=horizon,
                                monitoring_focus=monitoring_focus,
                                source_run_type="daily" if r.get("run_id") else "intraday",
                            )
                        ]
                        db.table("theses").insert({
                            "user_id": user_id,
                            "position_id": position_id,
                            "ticker": ticker,
                            "entry_thesis": r["thesis_text"],
                            "exit_conditions": combined_exit,
                            "horizon": horizon,
                            "play_type": r.get("play_type", "A"),
                            "status": "intact",
                            "notes_log": notes_log,
                        }).execute()
            except Exception as e:
                logger.warning("Thesis creation failed for %s: %s", ticker, e)

    # Mark confirmed only after successful trade execution
    db.table("recommendations").update({
        "status": "confirmed",
        "actual_price": data.actual_price,
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rec_id).execute()

    # Remove from watchlist: buy/add = ticker is now in portfolio
    if action in ("buy", "add"):
        try:
            from app.agent.watchlist_manager import remove_from_watchlist
            await remove_from_watchlist(user_id, ticker)
        except Exception as e:
            logger.warning("Watchlist cleanup failed for %s: %s", ticker, e)

    return {"status": "confirmed", "rec_id": rec_id}


@router.post("/{rec_id}/reject")
async def reject_recommendation(
    rec_id: str,
    data: RejectRequest,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()

    rec = (
        db.table("recommendations")
        .select("id, status, ticker")
        .eq("id", rec_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not rec.data:
        raise HTTPException(status_code=404, detail="Doporučení nenalezeno")
    if rec.data[0]["status"] not in ("pending", "updated"):
        raise HTTPException(status_code=400, detail="Doporučení již bylo zpracováno")

    ticker = rec.data[0].get("ticker", "")

    db.table("recommendations").update({
        "status": "rejected",
        "rejection_reason": data.reason,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rec_id).execute()

    # Remove from watchlist on reject — agent re-adds if signal returns
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
