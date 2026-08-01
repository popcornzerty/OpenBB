"""Éligibilité au PEA.

Règle légale : est éligible l'action d'une société dont le **siège social** se
situe dans l'Espace économique européen — UE 27 + Islande, Norvège,
Liechtenstein — et soumise à l'impôt sur les sociétés ou équivalent.

Le **lieu de cotation n'entre pas en compte** : Airbus, cotée à Paris mais dont
le siège est aux Pays-Bas, est éligible ; une société suisse ou britannique
cotée à Paris ne l'est pas (le Royaume-Uni est sorti de l'EEE avec le Brexit).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: UE 27.
EU_27 = {
    "AT": "Autriche",
    "BE": "Belgique",
    "BG": "Bulgarie",
    "CY": "Chypre",
    "CZ": "Tchéquie",
    "DE": "Allemagne",
    "DK": "Danemark",
    "EE": "Estonie",
    "ES": "Espagne",
    "FI": "Finlande",
    "FR": "France",
    "GR": "Grèce",
    "HR": "Croatie",
    "HU": "Hongrie",
    "IE": "Irlande",
    "IT": "Italie",
    "LT": "Lituanie",
    "LU": "Luxembourg",
    "LV": "Lettonie",
    "MT": "Malte",
    "NL": "Pays-Bas",
    "PL": "Pologne",
    "PT": "Portugal",
    "RO": "Roumanie",
    "SE": "Suède",
    "SI": "Slovénie",
    "SK": "Slovaquie",
}

#: Les trois États AELE membres de l'EEE (la Suisse est AELE mais **pas** EEE).
EEA_EXTRA = {"IS": "Islande", "LI": "Liechtenstein", "NO": "Norvège"}

#: EEE-30 : périmètre géographique du PEA.
EEA = {**EU_27, **EEA_EXTRA}

#: Pays hors EEE que l'on croise sur les places européennes.
#:
#: Sert uniquement à l'affichage : sans cela, une valeur suisse s'affiche
#: « Switzerland » au milieu d'une liste en français.
NON_EEA_LABELS = {
    "CH": "Suisse",
    "GB": "Royaume-Uni",
    "US": "États-Unis",
    "JE": "Jersey",
    "GG": "Guernesey",
    "IM": "Île de Man",
    "GI": "Gibraltar",
    "BM": "Bermudes",
    "KY": "Îles Caïmans",
    "VG": "Îles Vierges britanniques",
    "MC": "Monaco",
    "TR": "Turquie",
    "RU": "Russie",
    "IL": "Israël",
    "CA": "Canada",
    "JP": "Japon",
    "CN": "Chine",
    "AU": "Australie",
}


def country_label(iso: str | None, fallback: str | None = None) -> str | None:
    """Libellé français d'un pays, EEE ou non."""
    if not iso:
        return fallback
    return EEA.get(iso) or NON_EEA_LABELS.get(iso) or fallback or iso

#: Libellés de pays renvoyés par les providers -> code ISO-3166 alpha-2.
_COUNTRY_TO_ISO = {
    # EEE
    "austria": "AT", "autriche": "AT", "österreich": "AT",
    "belgium": "BE", "belgique": "BE", "belgië": "BE",
    "bulgaria": "BG", "bulgarie": "BG",
    "croatia": "HR", "croatie": "HR", "hrvatska": "HR",
    "cyprus": "CY", "chypre": "CY",
    "czech republic": "CZ", "czechia": "CZ", "tchéquie": "CZ",
    "denmark": "DK", "danemark": "DK", "danmark": "DK",
    "estonia": "EE", "estonie": "EE",
    "finland": "FI", "finlande": "FI", "suomi": "FI",
    "france": "FR",
    "germany": "DE", "allemagne": "DE", "deutschland": "DE",
    "greece": "GR", "grèce": "GR", "grece": "GR",
    "hungary": "HU", "hongrie": "HU",
    "iceland": "IS", "islande": "IS",
    "ireland": "IE", "irlande": "IE",
    "italy": "IT", "italie": "IT", "italia": "IT",
    "latvia": "LV", "lettonie": "LV",
    "liechtenstein": "LI",
    "lithuania": "LT", "lituanie": "LT",
    "luxembourg": "LU", "luxemburg": "LU",
    "malta": "MT", "malte": "MT",
    "netherlands": "NL", "pays-bas": "NL", "the netherlands": "NL", "nederland": "NL",
    "norway": "NO", "norvège": "NO", "norge": "NO",
    "poland": "PL", "pologne": "PL", "polska": "PL",
    "portugal": "PT",
    "romania": "RO", "roumanie": "RO",
    "slovakia": "SK", "slovaquie": "SK",
    "slovenia": "SI", "slovénie": "SI",
    "spain": "ES", "espagne": "ES", "españa": "ES",
    "sweden": "SE", "suède": "SE", "sverige": "SE",
    # Hors EEE fréquemment rencontrés sur les places européennes
    "united kingdom": "GB", "royaume-uni": "GB", "great britain": "GB", "england": "GB",
    "switzerland": "CH", "suisse": "CH", "schweiz": "CH",
    "united states": "US", "usa": "US", "united states of america": "US",
    "jersey": "JE", "guernsey": "GG", "isle of man": "IM", "gibraltar": "GI",
    "bermuda": "BM", "cayman islands": "KY", "british virgin islands": "VG",
    "monaco": "MC", "turkey": "TR", "türkiye": "TR", "russia": "RU",
    "israel": "IL", "canada": "CA", "japan": "JP", "china": "CN", "australia": "AU",
}

#: Cas où le pays publié par le provider ne correspond pas au **siège statutaire**.
#:
#: Le champ ``country`` de Yahoo reflète l'adresse opérationnelle, qui diverge
#: parfois du siège légal — seul ce dernier détermine l'éligibilité PEA.
#: Exemple canonique : STMicroelectronics N.V. est immatriculée aux Pays-Bas
#: (donc éligible) alors que son siège opérationnel est à Genève.
SEAT_OVERRIDES: dict[str, tuple[str, str]] = {
    "STMPA.PA": ("NL", "STMicroelectronics N.V. est immatriculée aux Pays-Bas"),
    "STM.MI": ("NL", "STMicroelectronics N.V. est immatriculée aux Pays-Bas"),
    "AIR.PA": ("NL", "Airbus SE est une société européenne de droit néerlandais"),
    "STLAP.PA": ("NL", "Stellantis N.V. est immatriculée aux Pays-Bas"),
    "STLAM.MI": ("NL", "Stellantis N.V. est immatriculée aux Pays-Bas"),
    "RACE.MI": ("NL", "Ferrari N.V. est immatriculée aux Pays-Bas"),
    "MT.AS": ("LU", "ArcelorMittal S.A. est luxembourgeoise"),
    "APAM.AS": ("LU", "Aperam S.A. est luxembourgeoise"),
    "TEN.MI": ("LU", "Tenaris S.A. est luxembourgeoise"),
    "EXO.AS": ("NL", "Exor N.V. est immatriculée aux Pays-Bas"),
    "PRX.AS": ("NL", "Prosus N.V. est immatriculée aux Pays-Bas"),
    # Siège opérationnel à Londres, mais société de droit espagnol : le
    # provider renvoie « United Kingdom », ce qui produirait un faux négatif.
    "IAG.MC": ("ES", "International Consolidated Airlines Group S.A. a son siège à Madrid"),
    # Cotée sur Euronext Amsterdam mais de droit suisse : faux positif évident
    # si l'on se fiait à la place de cotation.
    "DSFIR.AS": ("CH", "DSM-Firmenich AG est de droit suisse, siège à Kaiseraugst"),
    # Pays du siège non renvoyé par le provider — renseigné explicitement
    # plutôt que laissé indéterminé.
    "ML.PA": ("FR", "Compagnie Générale des Établissements Michelin, siège à Clermont-Ferrand"),
    "FDJ.PA": ("FR", "FDJ United, siège en France"),
    "ALD.PA": ("FR", "Ayvens S.A., siège en France"),
    "URW.AS": ("FR", "Unibail-Rodamco-Westfield SE est une société européenne de droit français"),
    "SCHA.OL": ("NO", "Schibsted ASA, siège à Oslo"),
    "O2D.DE": ("DE", "Telefónica Deutschland Holding AG, siège à Munich"),
    "GVOLT.LS": ("PT", "Greenvolt, siège au Portugal"),
}


class Eligibility(str, Enum):
    """Statut d'éligibilité PEA."""

    ELIGIBLE = "eligible"
    NON_ELIGIBLE = "non_eligible"
    #: Pays du siège indisponible — on ne tranche pas.
    UNKNOWN = "inconnu"


@dataclass(frozen=True)
class PeaStatus:
    """Verdict d'éligibilité, avec sa justification."""

    status: Eligibility
    country_iso: str | None
    country_label: str | None
    reason: str

    @property
    def is_eligible(self) -> bool:
        return self.status is Eligibility.ELIGIBLE

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "country_iso": self.country_iso,
            "country_label": self.country_label,
            "reason": self.reason,
        }


def normalize_country(value: str | None) -> str | None:
    """Convertit un libellé de pays en code ISO-3166 alpha-2, ou ``None``."""
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Déjà un code ISO alpha-2 ?
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    return _COUNTRY_TO_ISO.get(raw.casefold())


def assess(symbol: str | None, hq_country: str | None) -> PeaStatus:
    """Évalue l'éligibilité PEA d'un titre.

    ``symbol`` sert uniquement à consulter la table d'exceptions ; le verdict
    repose sur le pays du siège.
    """
    override = SEAT_OVERRIDES.get((symbol or "").upper())
    if override is not None:
        iso, note = override
        label = country_label(iso) or iso
        if iso in EEA:
            return PeaStatus(
                Eligibility.ELIGIBLE, iso, label,
                f"Siège statutaire dans l'EEE ({label}) — {note}.",
            )
        return PeaStatus(
            Eligibility.NON_ELIGIBLE, iso, label,
            f"Siège statutaire hors EEE ({label}) — {note}.",
        )

    iso = normalize_country(hq_country)
    if iso is None:
        return PeaStatus(
            Eligibility.UNKNOWN, None, hq_country or None,
            "Pays du siège indisponible : l'éligibilité ne peut pas être établie.",
        )

    if iso in EEA:
        return PeaStatus(
            Eligibility.ELIGIBLE, iso, EEA[iso],
            f"Siège social dans l'EEE ({EEA[iso]}).",
        )

    label = country_label(iso, hq_country)
    return PeaStatus(
        Eligibility.NON_ELIGIBLE, iso, label,
        f"Siège social hors EEE ({label}) : hors du périmètre PEA.",
    )
