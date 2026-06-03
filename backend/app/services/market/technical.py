"""
Technical indicators — RSI, SMA50/200, MACD, trend signal.
Uses yf.Ticker(t).history — cache 2h.
"""
import yfinance as yf
import pandas as pd
import json
import logging
from typing import Optional, Dict
from app.core.cache import CacheTTL
from app.services.market.quotes import safe_float

logger = logging.getLogger(__name__)


def _calc_rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    last = rsi.iloc[-1]
    return safe_float(last) if pd.notna(last) else None


def _trend_signal(price: float, sma50: Optional[float], sma200: Optional[float]) -> str:
    if sma50 and sma200:
        if price > sma50 > sma200:
            return "strong_bullish"
        if price > sma50 and price > sma200:
            return "bullish"
        if price < sma50 < sma200:
            return "strong_bearish"
        if price < sma50 and price < sma200:
            return "bearish"
    return "mixed"


async def get_technicals(redis, ticker: str) -> Dict:
    cache_key = f"ss:technicals:{ticker}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    result = {
        "ticker": ticker,
        "price": None,
        "rsi14": None,
        "sma50": None,
        "sma200": None,
        "macd_trend": None,
        "trend_signal": "mixed",
        "volume_vs_avg": None,
    }

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d")

        if hist.empty or len(hist) < 50:
            logger.warning("Insufficient history for %s", ticker)
            await redis.set(cache_key, json.dumps(result), ex=CacheTTL.TECHNICALS)
            return result

        close = hist["Close"]
        volume = hist["Volume"]

        rsi = _calc_rsi(close)
        sma50 = safe_float(close.rolling(50).mean().iloc[-1])
        sma200 = safe_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        price = safe_float(close.iloc[-1])

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_trend = "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish"

        avg_vol = volume.tail(20).mean()
        current_vol = volume.iloc[-1]
        volume_vs_avg = round(current_vol / avg_vol, 2) if avg_vol > 0 else None

        result.update({
            "price": price,
            "rsi14": rsi,
            "sma50": sma50,
            "sma200": sma200,
            "macd_trend": macd_trend,
            "trend_signal": _trend_signal(price or 0, sma50, sma200),
            "volume_vs_avg": volume_vs_avg,
        })

    except Exception as e:
        logger.warning("Technicals fetch failed for %s: %s", ticker, e)

    await redis.set(cache_key, json.dumps(result), ex=CacheTTL.TECHNICALS)
    return result
