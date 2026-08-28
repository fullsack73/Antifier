"""Ticker aliases required by external market-data providers."""


YAHOO_TICKER_ALIASES = {
    "BF.A": "BF-A",
    "BF.B": "BF-B",
    "BRK.A": "BRK-A",
    "BRK.B": "BRK-B",
}


def normalize_yahoo_ticker(value):
    ticker = str(value or "").strip().upper()
    return YAHOO_TICKER_ALIASES.get(ticker, ticker)
