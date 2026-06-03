"""
LiteLLM client — single call interface for all Claude API calls.
"""
import litellm
import logging
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

litellm.set_verbose = False


async def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = None) -> str:
    """
    Call Claude via LiteLLM. Returns response content string.
    Raises on API error.
    """
    import os
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    response = await litellm.acompletion(
        model=settings.ai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens or settings.ai_max_tokens,
    )
    content = response.choices[0].message.content
    logger.info("LLM call completed, tokens: %s", response.usage.total_tokens if response.usage else "?")
    return content or ""
