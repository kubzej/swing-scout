"""
Quote fetching — batch prices + FX rates.

Uses yf.download() for one-request batch fetching.
Never loops yf.Ticker(t).info for a list — always batch.
Redis cache: 5 min for quotes, 1 hour for FX rates.
"""
import yfinance as yf
import pandas as pd
import json
import logging
import math
from typing import List, Dict, Optional
from app.core.cache import CacheTTL

logger = logging.getLogger(__name__)

FX_TICKERS = {
    "USD_CZK": "USDCZK=X",
    "EUR_CZK": "EURCZK=X",
    "GBP_CZK": "GBPCZK=X",
}

FX_DERIVED_TICKERS = {
    "USD_HKD": "USDHKD=X",
}


def safe_float(value, decimals: int = 4) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, decimals)
    except (ValueError, TypeError):
        return None


def _normalize_ticker_data(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    ticker = ticker.upper()
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    for level in range(df.columns.nlevels):
        try:
            level_values = df.columns.get_level_values(level)
            if ticker in level_values:
                ticker_data = df.xs(ticker, level=level, axis=1)
                if isinstance(ticker_data, pd.Series):
                    ticker_data = ticker_data.to_frame()
                if isinstance(ticker_data.columns, pd.MultiIndex):
                    ticker_data.columns = ticker_data.columns.get_level_values(0)
                return ticker_data
        except (KeyError, IndexError, ValueError):
            continue
    unique_tickers = set(df.columns.get_level_values(df.columns.nlevels - 1))
    if len(unique_tickers) == 1 and ticker in unique_tickers:
        ticker_data = df.copy()
        ticker_data.columns = ticker_data.columns.get_level_values(0)
        return ticker_data
    return None


async def get_quotes(redis, tickers: List[str]) -> Dict[str, dict]:
    if not tickers:
        return {}

    results: Dict[str, dict] = {}
    missing: List[str] = []

    for t in tickers:
        cached = await redis.get(f"ss:quote:{t}")
        if cached:
            results[t] = json.loads(cached)
        else:
            missing.append(t)

    if not missing:
        return results

    try:
        df = yf.download(
            " ".join(missing),
            period="2d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
        )

        if df.empty:
            logger.warning("yf.download() returned empty for %s", missing)
            return results

        for t in missing:
            try:
                ticker_data = _normalize_ticker_data(df, t)
                if ticker_data is None or ticker_data.empty:
                    continue
                if "Close" not in ticker_data.columns:
                    continue
                ticker_data = ticker_data.dropna(subset=["Close"])
                if ticker_data.empty:
                    continue

                latest = ticker_data.iloc[-1]
                price = safe_float(latest["Close"])
                if price is None:
                    continue

                volume = int(latest.get("Volume", 0) or 0)
                prev_close = None
                change_pct = 0.0

                if len(ticker_data) >= 2:
                    prev_close = safe_float(ticker_data.iloc[-2]["Close"])
                    if prev_close and prev_close > 0:
                        change_pct = safe_float((price - prev_close) / prev_close * 100) or 0.0

                quote = {
                    "ticker": t,
                    "price": price,
                    "yesterday_close": prev_close,
                    "change_pct": change_pct,
                    "volume": volume,
                }
                results[t] = quote
                await redis.set(f"ss:quote:{t}", json.dumps(quote), ex=CacheTTL.QUOTE_BASIC)

            except Exception as e:
                logger.warning("Failed to process quote for %s: %s", t, e)

    except Exception as e:
        logger.error("yf.download() failed: %s", e)

    return results


async def get_fx_rates(redis) -> Dict[str, float]:
    cached = await redis.get("ss:fx_rates")
    if cached:
        return json.loads(cached)

    rates: Dict[str, float] = {
        "USD_CZK": 23.0,
        "EUR_CZK": 25.0,
        "GBP_CZK": 29.0,
        "HKD_CZK": 3.0,
    }

    try:
        symbols = list(FX_TICKERS.values()) + list(FX_DERIVED_TICKERS.values())
        df = yf.download(
            " ".join(symbols),
            period="2d",
            interval="1d",
            auto_adjust=False,
            progress=False,
        )
        if not df.empty:
            for key, symbol in FX_TICKERS.items():
                try:
                    ticker_data = _normalize_ticker_data(df, symbol)
                    if ticker_data is None or ticker_data.empty or "Close" not in ticker_data.columns:
                        continue
                    close_series = ticker_data["Close"].dropna()
                    if close_series.empty:
                        continue
                    val = safe_float(close_series.iloc[-1])
                    if val:
                        rates[key] = val
                except Exception as e:
                    logger.warning("FX ticker %s processing failed: %s", symbol, e)

            # Yahoo often lacks a direct HKD/CZK quote. Derive it from USD/CZK and USD/HKD.
            try:
                usd_hkd_symbol = FX_DERIVED_TICKERS["USD_HKD"]
                usd_hkd_data = _normalize_ticker_data(df, usd_hkd_symbol)
                if (
                    usd_hkd_data is not None
                    and not usd_hkd_data.empty
                    and "Close" in usd_hkd_data.columns
                ):
                    usd_hkd_close = usd_hkd_data["Close"].dropna()
                    usd_hkd = safe_float(usd_hkd_close.iloc[-1]) if not usd_hkd_close.empty else None
                    usd_czk = rates.get("USD_CZK")
                    if usd_hkd and usd_hkd > 0 and usd_czk:
                        rates["HKD_CZK"] = round(usd_czk / usd_hkd, 4)
            except Exception as e:
                logger.warning("Derived HKD_CZK calculation failed: %s", e)
    except Exception as e:
        logger.warning("FX rates fetch failed, using defaults: %s", e)

    await redis.set("ss:fx_rates", json.dumps(rates), ex=CacheTTL.FX_RATES)
    return rates


FX_FALLBACKS: Dict[str, float] = {
    "USD_CZK": 23.0,
    "EUR_CZK": 25.0,
    "GBP_CZK": 29.0,
    "HKD_CZK": 3.0,
}


def get_fx_rate(currency: str, fx: Dict[str, float]) -> float:
    """Return CZK rate for given currency. Logs warning on fallback."""
    if currency == "CZK":
        return 1.0
    key = f"{currency}_CZK"
    if key in fx:
        return fx[key]
    fallback = FX_FALLBACKS.get(key)
    if fallback:
        logger.warning("FX rate for %s not in cache, using hardcoded fallback %.2f", key, fallback)
        return fallback
    logger.error("No FX rate for %s — defaulting to 1.0, values will be WRONG", key)
    return 1.0


def to_czk(amount: float, currency: str, fx: Dict[str, float]) -> float:
    return round(amount * get_fx_rate(currency, fx), 2)
