"""LiteLLM client — single call interface for all Claude API calls."""
import logging
import os
from time import perf_counter

import litellm

from app.core.config import get_settings
from app.core.run_logging import log_event

logger = logging.getLogger(__name__)
settings = get_settings()

litellm.set_verbose = False


async def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = None,
    label: str | None = None,
) -> str:
    """Call Claude via LiteLLM. Returns response content string."""
    label = label or 'anonymous'
    requested_max_tokens = max_tokens or settings.ai_max_tokens
    os.environ['ANTHROPIC_API_KEY'] = settings.anthropic_api_key

    log_event(
        logger,
        logging.INFO,
        'llm_call_started',
        label=label,
        model=settings.ai_model,
        system_chars=len(system_prompt),
        user_chars=len(user_prompt),
        max_tokens=requested_max_tokens,
    )
    start = perf_counter()

    try:
        response = await litellm.acompletion(
            model=settings.ai_model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=requested_max_tokens,
        )
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            'llm_call_failed',
            label=label,
            model=settings.ai_model,
            duration_ms=round((perf_counter() - start) * 1000),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    usage = response.usage
    log_event(
        logger,
        logging.INFO,
        'llm_call_completed',
        label=label,
        model=settings.ai_model,
        duration_ms=round((perf_counter() - start) * 1000),
        total_tokens=getattr(usage, 'total_tokens', None),
        prompt_tokens=getattr(usage, 'prompt_tokens', None),
        completion_tokens=getattr(usage, 'completion_tokens', None),
    )
    content = response.choices[0].message.content
    return content or ''
