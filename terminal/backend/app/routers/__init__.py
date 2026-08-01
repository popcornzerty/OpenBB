"""Routes HTTP du terminal."""

from . import company, market, screener, search, valuation, watchlist

ROUTERS = [
    market.router,
    search.router,
    company.router,
    screener.router,
    valuation.router,
    watchlist.router,
]

__all__ = ["ROUTERS"]
