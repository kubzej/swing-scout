"""
Retroactive thesis generation — called when user logs a non-recommended trade.
Fetches news and generates a structured thesis via Claude API.
"""
import json
import logging
from app.ai.client import call_llm
from app.search.client import search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Jsi asistent investičního analytika SwingScout. Tvým úkolem je napsat strukturovanou investiční tezi pro zadanou pozici na základě dostupných informací.

Vrať POUZE JSON v tomto formátu:
{
  "entry_thesis": "Krátká hlavní teze (1-2 věty, proč je akcie zajímavá)",
  "entry_rationale": "Konkrétní důvod vstupu a katalyzátor",
  "invalidation_conditions": "Kdy je teze špatně a pozici zavřít",
  "profit_taking_plan": "Kdy a jak vybírat zisky (target cena nebo podmínka)",
  "monitoring_focus": "Co konkrétně sledovat po dobu držení",
  "holding_horizon": "Předpokládaný horizont držení",
  "add_plan": null,
  "exit_plan": null,
  "play_type": "A"
}

Pokud informace nestačí pro konkrétní odpověď, použij: "Doplň ručně."
Vrať pouze JSON, bez dalšího textu."""


async def generate_retroactive_thesis(
    ticker: str,
    action: str,
    price: float,
    play_type: str = "A",
) -> dict:
    """
    Generate structured entry thesis for a manually logged trade.
    Returns dict with v2 thesis fields.
    """
    news_context = ""
    try:
        results = await search(f"{ticker} stock news analysis {action}", max_results=3, days=30)
        if results:
            news_context = "\n".join(
                f"- {r.get('title', '')}: {r.get('content', '')[:200]}"
                for r in results[:3]
            )
    except Exception as e:
        logger.warning("News fetch failed for retroactive thesis %s: %s", ticker, e)

    play_label = {
        "A": "Fundamentální long (Type A)",
        "B": "Katalyzátor/narrativ (Type B)",
        "C": "Momentum (Type C)",
    }.get(play_type, "Fundamentální long (Type A)")

    horizon_default = {
        "A": "Týdny až měsíce",
        "B": "Eventová — závisí na katalyzátoru",
        "C": "Dny až týdny",
    }.get(play_type, "Týdny až měsíce")

    user_prompt = f"""Uživatel právě {('nakoupil' if action == 'buy' else 'prodal')} {ticker} za cenu ${price:.2f}.

Typ hry: {play_label}

Dostupné informace z webu:
{news_context or 'Žádné dostupné informace.'}

Napiš strukturovanou investiční tezi pro tuto pozici. Odpovídej v češtině."""

    fallback = {
        "entry_thesis": f"Manuálně zadaná pozice {ticker} — thesis nebyla automaticky vygenerována.",
        "entry_rationale": "Doplň ručně.",
        "invalidation_conditions": "Doplň ručně.",
        "profit_taking_plan": "Doplň ručně.",
        "monitoring_focus": "Doplň ručně.",
        "holding_horizon": horizon_default,
        "add_plan": None,
        "exit_plan": None,
        "play_type": play_type,
    }

    try:
        response_text = await call_llm(SYSTEM_PROMPT, user_prompt, max_tokens=600, label=f'retroactive_thesis:{ticker}')
        parsed = _parse_thesis_json(response_text)
        if parsed:
            parsed.setdefault("play_type", play_type)
            parsed.setdefault("holding_horizon", horizon_default)
            # Ensure all required keys exist
            for key in fallback:
                if key not in parsed or parsed[key] is None:
                    parsed[key] = fallback[key]
            return parsed
    except Exception as e:
        logger.error("LLM call failed for retroactive thesis %s: %s", ticker, e)

    return fallback


def _parse_thesis_json(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    # Try to extract JSON block
    import re
    match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
