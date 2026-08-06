"""Configuration du terminal.

Toutes les valeurs sont surchargeables par variable d'environnement (préfixe ``PEATERM_``)
ou par un fichier ``.env`` placé à la racine de ``terminal/backend``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(f"PEATERM_{name}", default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Réglages du terminal."""

    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8801))

    #: Répertoire de travail (cache, watchlists).
    state_dir: Path = field(
        default_factory=lambda: Path(
            _env("STATE_DIR", str(Path.home() / ".pea-terminal"))
        )
    )

    # --- Durées de vie du cache, en secondes -------------------------------
    #: Les cotations Euronext/XETRA passant par Yahoo sont différées ~15 min ;
    #: rafraîchir plus vite que 60 s ne fait qu'ajouter du trafic sans gagner
    #: d'information.
    ttl_quote: int = field(default_factory=lambda: _env_int("TTL_QUOTE", 60))
    ttl_intraday: int = field(default_factory=lambda: _env_int("TTL_INTRADAY", 300))
    ttl_historical: int = field(default_factory=lambda: _env_int("TTL_HISTORICAL", 3600))
    ttl_profile: int = field(default_factory=lambda: _env_int("TTL_PROFILE", 86400))
    ttl_fundamentals: int = field(
        default_factory=lambda: _env_int("TTL_FUNDAMENTALS", 86400)
    )
    ttl_news: int = field(default_factory=lambda: _env_int("TTL_NEWS", 900))
    ttl_search: int = field(default_factory=lambda: _env_int("TTL_SEARCH", 86400))

    # --- Moteur de valorisation -------------------------------------------
    #: Profondeur de l'historique utilisée pour calculer les multiples médians.
    #: 5 ans est le plafond des sources gratuites (Yahoo s'arrête à 5 exercices
    #: annuels). Porter à 10 dès qu'une source payante est branchée.
    valuation_window_years: int = field(
        default_factory=lambda: _env_int("VALUATION_WINDOW_YEARS", 5)
    )
    #: Nombre d'années réellement affichées dans l'UI.
    valuation_display_years: int = field(
        default_factory=lambda: _env_int("VALUATION_DISPLAY_YEARS", 5)
    )
    #: Horizon du prolongement en pointillé, en mois.
    valuation_projection_months: int = field(
        default_factory=lambda: _env_int("VALUATION_PROJECTION_MONTHS", 18)
    )
    #: Fenêtre de lissage de la courbe, en jours de bourse.
    valuation_smoothing_days: int = field(
        default_factory=lambda: _env_int("VALUATION_SMOOTHING_DAYS", 63)
    )
    #: Amplitude maximale de la prime/décote qualité.
    valuation_quality_cap: float = field(
        default_factory=lambda: float(_env("VALUATION_QUALITY_CAP", "0.15"))
    )

    # --- Sources payantes, optionnelles ------------------------------------
    #
    # Le terminal fonctionne intégralement sans aucune clé. En poser une lève
    # deux plafonds de la source gratuite : la profondeur des états financiers
    # (quatre exercices publiés chez Yahoo) et l'étendue du consensus (chiffre
    # d'affaires et bénéfice par action seulement, sur deux exercices).
    #
    # Aucune bascule automatique de facturation : la présence de la clé est le
    # seul déclencheur, et son absence laisse tout le monde sur le gratuit.
    fmp_api_key: str = field(default_factory=lambda: _env("FMP_API_KEY", ""))
    intrinio_api_key: str = field(default_factory=lambda: _env("INTRINIO_API_KEY", ""))

    #: Profondeur d'états financiers demandée quand une clé est posée. Yahoo
    #: plafonne à 5 (dont un exercice vide) ; FMP et Intrinio remontent bien
    #: au-delà.
    premium_statement_limit: int = field(
        default_factory=lambda: _env_int("PREMIUM_STATEMENT_LIMIT", 10)
    )

    @property
    def premium_provider(self) -> str | None:
        """Fournisseur payant configuré, le cas échéant.

        Intrinio passe devant : il couvre ``forward_sales`` et ``forward_pe``
        là où FMP s'arrête au bénéfice et à l'EBITDA.
        """
        if self.intrinio_api_key:
            return "intrinio"
        if self.fmp_api_key:
            return "fmp"
        return None

    @property
    def fundamentals_provider(self) -> str:
        return self.premium_provider or "yfinance"

    @property
    def statement_limit(self) -> int:
        """Nombre d'exercices demandés aux états financiers.

        Sans clé, le plafond est celui d'OpenBB pour yfinance — au-delà,
        l'appel est rejeté par validation.
        """
        return self.premium_statement_limit if self.premium_provider else 5

    @property
    def cache_path(self) -> Path:
        return self.state_dir / "cache.sqlite"

    @property
    def watchlist_path(self) -> Path:
        return self.state_dir / "watchlists.json"


settings = Settings()
settings.state_dir.mkdir(parents=True, exist_ok=True)
