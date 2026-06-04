"""
Retroactive thesis generation — called when user logs a non-recommended trade.
Fetches fundamentals + news and generates a thesis via Claude API.
"""
import logging
from app.ai.client import call_llm
from app.search.client import search

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Jsi asistent investičního analytika SwingScout. Tvým úkolem je napsat krátkou investiční tezi pro zadanou akci na základě dostupných informací.

Teze musí obsahovat:
1. Proč je akcie zajímavá (1-2 věty)
2. Hlavní katalyzátor nebo důvod vstupu
3. Kdy je teze špatně a pozici zavřít
4. Kdy a jak vybírat zisky
5. Krátký horizont držení

Formát: prostý text, maximálně 150 slov, česky."""


async def generate_retroactive_thesis(
    ticker: str,
    action: str,
    price: float,
    play_type: str = "A",
) -> dict:
    """
    Generate entry thesis for a manually logged trade.
    Returns dict with entry_thesis, exit_conditions, horizon.
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

    user_prompt = f"""Uživatel právě {('nakoupil' if action == 'buy' else 'prodal')} {ticker} za cenu ${price:.2f}.

Typ hry: {'Fundamentální long (Type A)' if play_type == 'A' else 'Katalyzátor/narrativ (Type B)' if play_type == 'B' else 'Momentum (Type C)'}

Dostupné informace z webu:
{news_context or 'Žádné dostupné informace.'}

Napiš stručnou investiční tezi pro tuto pozici."""

    try:
        thesis_text = await call_llm(SYSTEM_PROMPT, user_prompt, max_tokens=400, label=f'retroactive_thesis:{ticker}')
    except Exception as e:
        logger.error("LLM call failed for retroactive thesis %s: %s", ticker, e)
        thesis_text = f"Manuálně zadaná pozice {ticker} — thesis nebyla automaticky vygenerována."

    horizon_map = {"A": "Týdny až měsíce", "B": "Eventová — závisí na katalyzátoru", "C": "Dny až týdny"}

    return {
        "entry_thesis": thesis_text,
        "exit_conditions": "Doplň ručně: kdy je teze špatně a kdy staged vybírat zisky.",
        "horizon": horizon_map.get(play_type, "Týdny až měsíce"),
        "play_type": play_type,
    }
