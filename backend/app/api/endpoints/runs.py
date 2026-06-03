from fastapi import APIRouter, Depends, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.auth import get_current_user_id
from app.core.supabase import get_supabase
from app.core.security import limiter
from starlette.requests import Request
import subprocess
import sys
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_runs(
    limit: int = 10,
    run_type: str = None,
    user_id: str = Depends(get_current_user_id),
):
    db = get_supabase()
    query = (
        db.table("daily_runs")
        .select("id, run_type, status, started_at, completed_at, error_message, market_regime, fng_score")
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(limit)
    )
    if run_type:
        query = query.eq("run_type", run_type)
    response = query.execute()
    return response.data or []


@router.get("/{run_id}")
async def get_run(run_id: str, user_id: str = Depends(get_current_user_id)):
    db = get_supabase()
    response = (
        db.table("daily_runs")
        .select("*")
        .eq("id", run_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Run nenalezen")
    return response.data[0]


@router.post("/trigger")
@limiter.limit("3/hour")
async def trigger_run(
    request: Request,
    run_type: str = "daily",
    user_id: str = Depends(get_current_user_id),
):
    """Trigger agent run asynchronously. Returns run_id immediately."""
    if run_type not in ("daily", "intraday"):
        raise HTTPException(status_code=400, detail="run_type musí být 'daily' nebo 'intraday'")

    env = {**os.environ, "AGENT_USER_ID": user_id}
    try:
        # cwd must be the backend/ project root so `python -m app.agent.runner` can import `app`
        backend_dir = os.environ.get(
            "WORKDIR",
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        )
        subprocess.Popen(
            [sys.executable, "-m", "app.agent.runner", "--type", run_type],
            env=env,
            cwd=backend_dir,
        )
        logger.info("Triggered %s run for user %s", run_type, user_id)
        return {"status": "triggered", "run_type": run_type}
    except Exception as e:
        logger.error("Failed to trigger run: %s", e)
        raise HTTPException(status_code=500, detail="Nepodařilo se spustit run")
