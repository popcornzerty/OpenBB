"""Taux de change de référence de la Banque centrale européenne.

Les capitalisations remontées par le provider sont exprimées en devise de
cotation : couronne danoise pour Novo Nordisk, couronne suédoise pour Investor,
zloty pour les valeurs polonaises. Les comparer ou les trier sans conversion
n'a aucun sens — un screener paneuropéen doit ramener tout le monde en euros.

La BCE publie ses taux de référence quotidiens en accès libre, sans clé.
"""

from __future__ import annotations

import csv
import io

import aiohttp

from ..cache import cache

_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
    "?lastNObservations=1&format=csvdata&detail=dataonly"
)

#: Un jour : les taux de référence BCE ne sont publiés qu'une fois par jour.
_TTL = 86_400

#: Devises arrimées à l'euro, utilisées si la BCE ne répond pas.
#: La couronne danoise est dans le MCE II, le lev bulgare en caisse d'émission.
_FALLBACK = {"EUR": 1.0, "DKK": 7.46, "BGN": 1.9558}


async def rates() -> dict[str, float]:
    """Taux de change : nombre d'unités de devise pour 1 euro."""

    async def produce() -> dict[str, float]:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_URL) as response:
                response.raise_for_status()
                payload = await response.text()

        table = {"EUR": 1.0}
        for row in csv.DictReader(io.StringIO(payload)):
            currency = (row.get("CURRENCY") or "").strip()
            raw = (row.get("OBS_VALUE") or "").strip()
            if not currency or not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if value > 0:
                table[currency] = value
        return table

    try:
        value, _, _ = await cache.resolve("ecb:rates", _TTL, produce)
        return value if value else dict(_FALLBACK)
    except Exception:  # noqa: BLE001
        # Un screener doit rester utilisable même si la BCE est injoignable.
        return dict(_FALLBACK)


async def to_eur(amount: float | None, currency: str | None) -> float | None:
    """Convertit un montant en euros. Renvoie ``None`` si la devise est inconnue.

    Mieux vaut une valeur absente qu'une valeur fausse : un montant non
    converti fausserait tout classement par capitalisation.
    """
    if amount is None:
        return None
    code = (currency or "EUR").strip().upper()
    if code == "EUR":
        return amount
    table = await rates()
    rate = table.get(code)
    if not rate:
        return None
    return amount / rate
