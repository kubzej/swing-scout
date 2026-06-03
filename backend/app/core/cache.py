class CacheTTL:
    # Market data
    QUOTE_BASIC = 300           # 5 min  — price, change, volume
    TECHNICALS = 7200           # 2 hours — RSI, SMA, MACD
    FINANCIALS = 86400          # 24 hours — fundamentals (changes quarterly)
    EARNINGS = 86400            # 24 hours — next earnings date
    FX_RATES = 3600             # 1 hour — USD/EUR/GBP/HKD → CZK

    # Agent / market context
    MARKET_CONTEXT = 14400      # 4 hours — F&G + SPY regime

    # AI
    AI_THESIS = 86400           # 24 hours — generated theses
