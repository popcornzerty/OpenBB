"""Application FastAPI du terminal PEA.

Le backend consomme OpenBB comme bibliothèque plutôt que de passer par
``openbb-platform-api`` : ce dernier expose génériquement l'intégralité des
endpoints OpenBB, alors qu'un terminal a besoin de l'inverse — peu de routes,
taillées pour l'interface, portant la logique PEA, le cache et la valorisation
côté serveur.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cache import cache
from .pea import registry
from .routers import ROUTERS
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("peaterm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.load()
    purged = cache.purge_expired()
    logger.info(
        "Univers chargé : %d valeurs — %d entrées de cache expirées purgées",
        len(registry.entries),
        purged,
    )
    if registry.is_empty:
        logger.warning(
            "Univers vide. Lancer : python scripts/build_universe.py "
            "pour construire data/universe_eu.csv."
        )
    yield
    cache.close()


app = FastAPI(
    title="Terminal PEA",
    description=(
        "Terminal d'investissement centré sur les actions européennes "
        "éligibles au PEA, bâti sur OpenBB."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Le frontend tourne soit sur le serveur de développement Vite, soit dans la
# webview Tauri. Sous Windows, celle-ci sert la page depuis
# `http://tauri.localhost` ; sous macOS et Linux depuis `tauri://localhost`.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?"
        r"|https?://tauri\.localhost"
        r"|tauri://localhost)$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in ROUTERS:
    app.include_router(router)


@app.get("/api/health", tags=["système"])
async def health() -> dict:
    """État du service et paramètres actifs."""
    return {
        "status": "ok",
        "universe_size": len(registry.entries),
        "valuation_window_years": settings.valuation_window_years,
        "data_note": (
            "Cotations Euronext/XETRA différées d'environ 15 minutes "
            "(source gratuite Yahoo)."
        ),
    }
