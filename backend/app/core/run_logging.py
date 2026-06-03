"""Run-scoped logging helpers for agent observability."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar, Token
from typing import Any

DEFAULT_LOG_CONTEXT = {
    'run_id': '-',
    'run_type': '-',
    'agent_user_id': '-',
}
LOG_FORMAT = (
    '%(asctime)s %(levelname)s %(name)s '
    '[run=%(run_id)s type=%(run_type)s user=%(agent_user_id)s] — %(message)s'
)

_run_log_context: ContextVar[dict[str, str]] = ContextVar('run_log_context', default=DEFAULT_LOG_CONTEXT.copy())


class RunContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = {**DEFAULT_LOG_CONTEXT, **_run_log_context.get()}
        record.run_id = context['run_id']
        record.run_type = context['run_type']
        record.agent_user_id = context['agent_user_id']
        return True


def configure_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=LOG_FORMAT)
    else:
        root_logger.setLevel(level)
        formatter = logging.Formatter(LOG_FORMAT)
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)

    for handler in root_logger.handlers:
        if not any(isinstance(existing, RunContextFilter) for existing in handler.filters):
            handler.addFilter(RunContextFilter())


def bind_run_context(**values: str) -> Token:
    current = {**DEFAULT_LOG_CONTEXT, **_run_log_context.get()}
    for key, value in values.items():
        current[key] = str(value)
    return _run_log_context.set(current)


def reset_run_context(token: Token) -> None:
    _run_log_context.reset(token)


def get_run_context() -> dict[str, str]:
    return {**DEFAULT_LOG_CONTEXT, **_run_log_context.get()}


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f'{value:.2f}'
    if isinstance(value, (dict, list, tuple)):
        encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
        return encoded if len(encoded) <= 400 else encoded[:397] + '...'
    return str(value)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    serialized = ' '.join(
        f'{key}={_format_value(value)}'
        for key, value in fields.items()
        if value is not None
    )
    message = f'event={event}'
    if serialized:
        message = f'{message} | {serialized}'
    logger.log(level, message)
