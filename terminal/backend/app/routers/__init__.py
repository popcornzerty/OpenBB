"""Routes HTTP du terminal."""

from . import company, market, screener, search, valuation, watchlist, wealthfolio

ROUTERS = [
    market.router,
    search.router,
    company.router,
    screener.router,
    valuation.router,
    watchlist.router,
    wealthfolio.router,
]

__all__ = ["ROUTERS"]
