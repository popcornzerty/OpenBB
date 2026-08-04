"""Dividende : rendement, sûreté et prochaine échéance estimée.

Module pur, sans réseau : la partie qui juge la solidité d'un dividende doit
pouvoir être vérifiée isolément, puisqu'elle produit un feu vert ou rouge sur
lequel une décision se prend.
"""

from __future__ import annotations

import datetime as dt
import statistics
from enum import Enum

#: Au-delà de ce taux de distribution, le dividende absorbe une part du
#: résultat qui laisse peu de marge à un exercice moins bon.
PAYOUT_STRETCHED = 0.60

#: Au-delà, le dividende dépasse le résultat : il est financé autrement que par
#: les bénéfices de l'exercice.
PAYOUT_UNCOVERED = 1.00

#: Part du flux de trésorerie libre absorbée par le dividende.
COVERAGE_STRETCHED = 0.80
COVERAGE_UNCOVERED = 1.00


class Safety(str, Enum):
    """Solidité apparente du dividende."""

    SAFE = "sur"
    STRETCHED = "tendu"
    UNCOVERED = "non_couvert"
    UNKNOWN = "inconnu"
    NONE = "aucun"


SAFETY_LABELS = {
    Safety.SAFE: "Sûr",
    Safety.STRETCHED: "Tendu",
    Safety.UNCOVERED: "Non couvert",
    Safety.UNKNOWN: "Indéterminé",
    Safety.NONE: "Pas de dividende",
}


def fcf_coverage(free_cash_flow: float | None, dividends_paid: float | None) -> float | None:
    """Part du flux de trésorerie libre absorbée par le dividende.

    ``dividends_paid`` est négatif dans le tableau de flux ; on raisonne sur sa
    valeur absolue. Un flux libre négatif renvoie une couverture supérieure à 1
    quel qu'en soit le montant : l'entreprise n'a rien généré à distribuer.
    """
    if free_cash_flow is None or dividends_paid is None:
        return None
    paid = abs(dividends_paid)
    if paid == 0:
        return 0.0
    if free_cash_flow <= 0:
        # Aucune couverture possible : on le signale par une valeur au-delà du
        # seuil, plutôt que par un nombre négatif difficile à lire.
        return float("inf")
    return paid / free_cash_flow


def safety(
    payout_ratio: float | None,
    coverage: float | None,
    dividend_yield: float | None,
) -> tuple[Safety, str]:
    """Verdict de sûreté, avec sa justification.

    Deux angles, et le plus défavorable l'emporte : le **taux de distribution**
    dit quelle part du résultat part en dividende, la **couverture par le flux
    de trésorerie libre** dit si l'argent existe réellement. Une société peut
    afficher un résultat confortable et ne dégager aucun cash — Engie distribue
    ainsi sur un flux libre négatif.
    """
    # Une société qui ne distribue rien ne mérite pas un feu vert : sans ce
    # test, un taux de distribution nul valait « sûr », et Adyen — qui n'a
    # jamais versé de dividende — arborait une pastille verte.
    no_yield = dividend_yield is None or dividend_yield <= 0
    no_payout = payout_ratio is None or payout_ratio <= 0
    if (dividend_yield is not None and dividend_yield <= 0) or (no_yield and no_payout):
        return Safety.NONE, "Cette société ne verse pas de dividende."

    if payout_ratio is None and coverage is None:
        return Safety.UNKNOWN, "Taux de distribution et couverture indisponibles."

    reasons: list[str] = []
    verdict = Safety.SAFE

    if payout_ratio is not None:
        if payout_ratio > PAYOUT_UNCOVERED:
            verdict = Safety.UNCOVERED
            reasons.append(
                f"le dividende dépasse le résultat ({payout_ratio * 100:.0f} % du bénéfice)"
            )
        elif payout_ratio > PAYOUT_STRETCHED:
            verdict = Safety.STRETCHED
            reasons.append(f"{payout_ratio * 100:.0f} % du bénéfice est distribué")
        else:
            reasons.append(f"{payout_ratio * 100:.0f} % du bénéfice distribué")

    if coverage is not None:
        if coverage > COVERAGE_UNCOVERED:
            verdict = Safety.UNCOVERED
            reasons.append(
                "le flux de trésorerie libre ne couvre pas le dividende"
                if coverage == float("inf")
                else f"il absorbe {coverage * 100:.0f} % du flux de trésorerie libre"
            )
        elif coverage > COVERAGE_STRETCHED:
            if verdict is Safety.SAFE:
                verdict = Safety.STRETCHED
            reasons.append(f"il absorbe {coverage * 100:.0f} % du flux de trésorerie libre")
        else:
            reasons.append(f"{coverage * 100:.0f} % du flux de trésorerie libre absorbé")

    return verdict, " ; ".join(reasons).capitalize() + "."


def _parse_dates(raw: list) -> list[dt.date]:
    dates: list[dt.date] = []
    for value in raw:
        if value is None:
            continue
        if isinstance(value, dt.datetime):
            dates.append(value.date())
        elif isinstance(value, dt.date):
            dates.append(value)
        else:
            try:
                dates.append(dt.date.fromisoformat(str(value)[:10]))
            except ValueError:
                continue
    return sorted(dates)


#: Profondeur d'historique retenue pour déduire le rythme actuel.
RHYTHM_WINDOW_YEARS = 4

#: Au-delà de ce multiple de l'intervalle habituel sans versement, le rythme
#: n'est plus crédible : le dividende a probablement été suspendu.
STALE_PERIODS = 2


def frequency(ex_dates: list) -> tuple[str, int | None]:
    """Rythme de versement, déduit des détachements passés.

    Renvoie ``(libellé, intervalle médian en jours)``.

    La fenêtre est **temporelle** et non un nombre de versements : une société
    passée d'un rythme annuel à trimestriel garderait sinon assez d'anciens
    versements dans la fenêtre pour que la médiane annonce « annuel » alors
    qu'elle verse tous les trimestres.
    """
    dates = _parse_dates(ex_dates)
    if not dates:
        return "inconnu", None

    horizon = dates[-1] - dt.timedelta(days=365 * RHYTHM_WINDOW_YEARS)
    recent = [d for d in dates if d >= horizon]
    if len(recent) < 3:
        # Historique trop clairsemé sur la fenêtre : on élargit plutôt que de
        # renoncer, un versement annuel n'en donnant que quatre en quatre ans.
        recent = dates[-4:]
    if len(recent) < 3:
        return "inconnu", None

    gaps = [(b - a).days for a, b in zip(recent, recent[1:]) if (b - a).days > 0]
    if not gaps:
        return "inconnu", None

    median = int(statistics.median(gaps))
    if median <= 45:
        return "mensuel", median
    if median <= 135:
        return "trimestriel", median
    if median <= 250:
        return "semestriel", median
    return "annuel", median


def next_ex_date(ex_dates: list, today: dt.date | None = None) -> dt.date | None:
    """Prochaine date de détachement, **estimée** à partir du rythme passé.

    Aucune source gratuite ne publie le calendrier à venir des dividendes
    européens. Cette date est donc une projection du rythme observé, pas une
    annonce de l'émetteur : l'interface doit le dire.

    Si le dernier détachement connu est déjà dans le futur — la source le
    publie parfois dès l'annonce — il est renvoyé tel quel, et c'est alors une
    date réelle.
    """
    today = today or dt.date.today()
    dates = _parse_dates(ex_dates)
    if not dates:
        return None

    last = dates[-1]
    if last > today:
        return last

    _, median = frequency(ex_dates)
    if median is None:
        return None

    # Un dividende dont le dernier versement remonte à plusieurs périodes a
    # probablement été suspendu : projeter le rythme passé annoncerait alors
    # une échéance qui ne viendra pas.
    if (today - last).days > median * STALE_PERIODS:
        return None

    projected = last + dt.timedelta(days=median)
    while projected <= today:
        projected += dt.timedelta(days=median)
    return projected
