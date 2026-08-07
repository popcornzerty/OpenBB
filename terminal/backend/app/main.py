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
from fastapi.responses import HTMLResponse

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


@app.get("/", include_in_schema=False)
async def racine() -> HTMLResponse:
    """Page d'accueil du service.

    Ce port sert l'API, pas l'interface. Sans cette page, y arriver par
    mégarde renvoyait un « Not Found » brut qui ne disait ni où était
    l'erreur, ni où aller.

    Le port de l'interface est un **réglage**, pas une détection : un client
    qui arrive ici n'est pas passé par le frontend, rien ne permet donc de
    savoir lequel l'a envoyé. La page l'annonce, faute de quoi une seconde
    instance mal configurée renverrait sereinement vers la première.
    """
    port_par_defaut = settings.frontend_port == 5180 and settings.port != 8801
    avertissement = (
        "<p class=\"alerte\">Ce port n'est pas celui par défaut, mais celui de "
        "l'interface l'est resté. Si l'adresse ci-dessus est la mauvaise, "
        "définissez <code>PEATERM_FRONTEND_PORT</code> au démarrage.</p>"
        if port_par_defaut
        else ""
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>Terminal PEA — service de données</title>
<style>
 body {{ font: 15px/1.6 system-ui, sans-serif; background: #0e1116; color: #c9d1d9;
        margin: 0; display: grid; place-items: center; min-height: 100vh; }}
 main {{ max-width: 34rem; padding: 2rem; }}
 h1 {{ font-size: 1.3rem; margin: 0 0 .4rem; color: #e6edf3; }}
 a {{ color: #5aa9ff; }}
 code {{ background: #161b22; padding: .1rem .35rem; border-radius: 4px; }}
 .note {{ color: #8b949e; font-size: 13px; margin-top: 1.4rem; }}
 .alerte {{ color: #d29922; font-size: 13px; border-left: 2px solid #d29922;
            padding-left: .7rem; }}
</style></head><body><main>
<h1>Vous êtes sur le service de données</h1>
<p>Ce port expose l'API du terminal, pas son interface.</p>
<p><strong>L'application se trouve sur
<a href="http://localhost:{settings.frontend_port}">http://localhost:{settings.frontend_port}</a></strong>
 — si elle ne répond pas, lancez <code>.\\start-dev.ps1</code>.</p>
{avertissement}
<p class="note">
 Ici : <a href="/docs">/docs</a> pour explorer l'API,
 <a href="/api/health">/api/health</a> pour l'état du service.
 Service sur le port {settings.port}. Univers chargé : {len(registry.entries)} valeurs.
</p>
</main></body></html>"""
    )


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
