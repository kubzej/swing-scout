"""
Agent runner — CLI entrypoint for Railway cron jobs.

Usage:
  python -m app.agent.runner --type daily
  python -m app.agent.runner --type intraday

User ID loaded from AGENT_USER_ID env var.
Exit code 0 = success, 1 = failure.
"""
import argparse
import asyncio
import logging
import os
import sys

from app.core.run_logging import bind_run_context, configure_logging, log_event, reset_run_context

configure_logging()
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description='SwingScout agent runner')
    parser.add_argument('--type', choices=['daily', 'intraday'], required=True)
    args = parser.parse_args()

    user_id = os.getenv('AGENT_USER_ID')
    if not user_id:
        logger.error('AGENT_USER_ID env var is not set')
        sys.exit(1)

    context_token = bind_run_context(run_type=args.type, agent_user_id=user_id)
    log_event(logger, logging.INFO, 'runner_started', run_type=args.type)

    try:
        if args.type == 'daily':
            from app.agent.daily_run import run_daily
            run_id = await run_daily(user_id)
            log_event(logger, logging.INFO, 'runner_completed', run_type=args.type, run_id=run_id)
        else:
            from app.agent.intraday_run import run_intraday
            count = await run_intraday(user_id)
            log_event(logger, logging.INFO, 'runner_completed', run_type=args.type, recommendations=count)

        sys.exit(0)

    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            'runner_failed',
            run_type=args.type,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        logger.error('%s run failed: %s', args.type, exc, exc_info=True)
        sys.exit(1)
    finally:
        reset_run_context(context_token)


if __name__ == '__main__':
    asyncio.run(main())
