"""
Agent runner — CLI entrypoint for Railway cron jobs.

Usage:
  python -m app.agent.runner --type daily
  python -m app.agent.runner --type intraday

User ID loaded from AGENT_USER_ID env var.
Exit code 0 = success, 1 = failure.
"""
import asyncio
import argparse
import logging
import sys
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="SwingScout agent runner")
    parser.add_argument("--type", choices=["daily", "intraday"], required=True)
    args = parser.parse_args()

    user_id = os.getenv("AGENT_USER_ID")
    if not user_id:
        logger.error("AGENT_USER_ID env var is not set")
        sys.exit(1)

    logger.info("Starting %s run for user %s", args.type, user_id)

    try:
        if args.type == "daily":
            from app.agent.daily_run import run_daily
            run_id = await run_daily(user_id)
            logger.info("Daily run completed: run_id=%s", run_id)
        else:
            from app.agent.intraday_run import run_intraday
            count = await run_intraday(user_id)
            logger.info("Intraday run completed: %d recommendations", count)

        sys.exit(0)

    except Exception as e:
        logger.error("%s run failed: %s", args.type, e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
