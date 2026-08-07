"""Routes HTTP du terminal."""

from . import (
    alerts,
    company,
    market,
    portfolio,
    screener,
    search,
    valuation,
    watchlist,
    wealthfolio,
)

ROUTERS = [
    market.router,
    search.router,
    company.router,
    screener.router,
    valuation.router,
    watchlist.router,
    wealthfolio.router,
    alerts.router,
    portfolio.router,
]

__all__ = ["ROUTERS"]
