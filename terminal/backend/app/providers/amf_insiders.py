"""Déclarations de dirigeants (initiés) publiées par l'AMF.

Article L. 621-18-2 du code monétaire et financier : un dirigeant, ou une
personne qui lui est étroitement liée, déclare ses opérations sur les titres
de sa société dans les trois jours ouvrés. L'AMF publie ces déclarations
quotidiennement dans sa base BDIF.

**Aucune API ouverte ici, contrairement aux franchissements de seuils.** La
BDIF est une application web ; ce module appelle les mêmes points d'entrée
que son interface. Rien n'en garantit la stabilité : une refonte du site
casserait l'extraction. C'est le compromis assumé pour disposer d'une donnée
que ni OpenBB ni aucun flux open-data vérifié ne fournit.

Trois étapes, chacune indispensable :

1. l'autocomplétion convertit une raison sociale en identifiant interne ;
2. l'index rend les déclarations de cette société, avec un lien PDF ;
3. le PDF, lui, porte le nom du déclarant, sa fonction et l'opération.

Les documents sont heureusement très structurés — champs étiquetés en
majuscules — ce qui rend l'extraction bien plus sûre que sur les avis de
franchissement, rédigés en prose.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import re
import urllib.parse
import urllib.request

from ..cache import cache

BASE = "https://bdif.amf-france.org/back/api"
USER_AGENT = "Mozilla/5.0 (compatible; terminal-pea/0.1)"

#: Les déclarations paraissent en fin de journée ; relire plus souvent est
#: inutile.
TTL_INDEX = 6 * 3600

#: Un identifiant de société ne change pas.
TTL_JETON = 30 * 86400

#: Une déclaration publiée est figée.
TTL_DOCUMENT = 30 * 86400

#: Plafond de documents analysés par appel : chaque PDF est une requête.
MAX_DOCUMENTS = 60

_MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

#: Les PDF de l'AMF emploient l'apostrophe typographique ; l'ignorer ferait
#: échouer chaque motif contenant « L'INSTRUMENT » ou « D'IDENTIFICATION ».
_APOS = "['’´]"


def _champ(motif: str) -> re.Pattern:
    return re.compile(motif, re.IGNORECASE)


_DECLARANT = _champ(
    r"PERSONNE\s+ETROITEMENT\s+LIEE\s*:\s*(?P<valeur>.{3,200}?)\s+NOTIFICATION"
)
#: La nature s'arrête au libellé suivant, quel qu'il soit : dans les
#: déclarations à plusieurs opérations, l'ordre des champs varie.
_NATURE = _champ(
    r"NATURE\s+DE\s+LA\s+TRANSACTION\s*:\s*(?P<valeur>.{3,60}?)"
    rf"\s+(?=DESCRIPTION|CODE|INFORMATION|DETAIL|PRIX|VOLUME|TRANSACTION|DATE|LIEU|L{_APOS})"
)
_DATE = _champ(r"DATE\s+DE\s+LA\s+TRANSACTION\s*:\s*(?P<valeur>\d{1,2}\s+\w+\s+20\d\d)")
_LIEU = _champ(r"LIEU\s+DE\s+LA\s+TRANSACTION\s*:\s*(?P<valeur>.{3,60}?)\s+NATURE")
_INSTRUMENT = _champ(
    rf"DESCRIPTION\s+DE\s+L{_APOS}INSTRUMENT\s+FINANCIER\s*:\s*(?P<valeur>.{{3,60}}?)\s+(?:CODE|INFORMATION)"
)
_ISIN = _champ(rf"CODE\s+D{_APOS}IDENTIFICATION[^:]{{0,40}}:\s*(?P<valeur>[A-Z]{{2}}[A-Z0-9]{{9}}\d)")
_AGREGE = _champ(
    r"INFORMATIONS\s+AGREGEES\s+PRIX\s*:\s*(?P<prix>[\d\s.,]+?)\s*(?P<devise>Euro|EUR|USD)"
    r".{0,40}?VOLUME\s*:\s*(?P<volume>[\d\s.,]+?)(?:\s+[A-Z]{2,}|\s*$)"
)
_EMETTEUR = _champ(r"EMETTEUR\s+NOM\s*:\s*(?P<valeur>.{2,80}?)\s+(?:LEI|DETAIL)")


def _nombre(texte: str | None) -> float | None:
    """Lit « 1 565.8029 » ou « 3 788,00 » en flottant."""
    if not texte:
        return None
    net = texte.replace(" ", "").replace(" ", "").replace(" ", "")
    # Les montants AMF utilisent le point décimal ; une virgule reste possible.
    if "," in net and "." not in net:
        net = net.replace(",", ".")
    else:
        net = net.replace(",", "")
    try:
        return float(net)
    except ValueError:
        return None


def _date_iso(texte: str | None) -> str | None:
    if not texte:
        return None
    parts = texte.lower().split()
    if len(parts) != 3 or parts[1] not in _MOIS:
        return None
    try:
        return dt.date(int(parts[2]), _MOIS[parts[1]], int(parts[0])).isoformat()
    except ValueError:
        return None


def _sens(nature: str | None) -> str | None:
    """Ramène la nature déclarée à un achat ou une vente.

    L'AMF distingue une dizaine de natures ; ce qui intéresse un porteur, au
    premier coup d'œil, c'est le sens. La nature exacte reste affichée à côté,
    car souscrire à un plan d'épargne salariale n'est pas acheter en bourse.
    """
    if not nature:
        return None
    n = nature.lower()
    if any(m in n for m in ("acquisition", "souscription", "achat", "attribution")):
        return "achat"
    if any(m in n for m in ("cession", "vente", "apport")):
        return "vente"
    return None


def parse(texte: str) -> dict:
    """Extrait les champs d'une déclaration de dirigeant."""

    def prendre(motif: re.Pattern, groupe: str = "valeur") -> str | None:
        m = motif.search(texte)
        if not m:
            return None
        return re.sub(r"\s+", " ", m.group(groupe)).strip(" ,;:.")

    brut_declarant = prendre(_DECLARANT)
    nom, fonction = brut_declarant, None
    if brut_declarant:
        # « SYLVAIN MONTCOUQUIOL, Directeur Général… » — le nom précède la
        # première virgule, la fonction suit. Les personnes morales liées
        # portent au contraire leur qualification dans le même souffle :
        # « GEST INVEST société civile personne morale liée à Philippe ROSIO ».
        tete, _, reste = brut_declarant.partition(",")
        if reste.strip():
            nom, fonction = tete.strip(), reste.strip()

    nature = prendre(_NATURE)
    agrege = _AGREGE.search(texte)
    return {
        "declarant": nom,
        "fonction": fonction,
        "emetteur": prendre(_EMETTEUR),
        "nature": nature,
        "sens": _sens(nature),
        "instrument": prendre(_INSTRUMENT),
        "isin": prendre(_ISIN),
        "lieu": prendre(_LIEU),
        "transaction_le": _date_iso(prendre(_DATE)),
        "prix": _nombre(agrege.group("prix")) if agrege else None,
        "devise": (agrege.group("devise") if agrege else None),
        "volume": _nombre(agrege.group("volume")) if agrege else None,
        "montant": (
            round(_nombre(agrege.group("prix")) * _nombre(agrege.group("volume")), 2)
            if agrege
            and _nombre(agrege.group("prix")) is not None
            and _nombre(agrege.group("volume")) is not None
            else None
        ),
    }


def _get_json(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str) -> str:
    import pypdf

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    pages = pypdf.PdfReader(io.BytesIO(raw)).pages
    return " ".join(" ".join((page.extract_text() or "").split()) for page in pages)


async def _jetons(raison_sociale: str) -> list[str]:
    """Identifiants BDIF correspondant à une raison sociale.

    Une société peut en porter plusieurs — historiques de dénomination — et
    les ignorer ferait manquer des déclarations.
    """

    async def produce():
        url = f"{BASE}/Autocomplete?Research={urllib.parse.quote(raison_sociale)}"
        try:
            payload = await asyncio.to_thread(_get_json, url)
        except Exception:  # noqa: BLE001
            return []
        cible = raison_sociale.strip().upper()
        trouves = []
        for item in payload.get("societesResult") or []:
            nom = (item.get("raisonSociale") or "").strip().upper()
            jeton = item.get("jeton")
            # L'autocomplétion est large : « SANOFI » ramène aussi des filiales.
            # On ne garde que les correspondances franches.
            if jeton and (nom == cible or nom.startswith(cible + " ")):
                trouves.append(jeton)
        return trouves

    key = f"amf:jeton:v1:{raison_sociale.strip().upper()}"
    value, _, _ = await cache.resolve(key, TTL_JETON, produce)
    return value


async def _index(jetons: list[str], since: dt.date) -> list[dict]:
    """Déclarations publiées depuis ``since`` pour ces identifiants."""
    if not jetons:
        return []

    params = [
        ("From", 0),
        ("Size", MAX_DOCUMENTS),
        ("TypesInformation", "DD"),
        ("SortField", "datePublication"),
        ("SortOrder", "desc"),
        *[("Jetons", j) for j in jetons],
    ]
    url = f"{BASE}/v1/informations?" + urllib.parse.urlencode(params)

    async def produce():
        try:
            payload = await asyncio.to_thread(_get_json, url)
        except Exception:  # noqa: BLE001
            return []
        rows = []
        for item in payload.get("result") or []:
            publie = (item.get("datePublication") or "")[:10]
            if publie < since.isoformat():
                continue
            docs = item.get("documents") or []
            societes = item.get("societes") or [{}]
            rows.append(
                {
                    "id": item.get("id"),
                    "numero": item.get("numero"),
                    "societe": societes[0].get("raisonSociale"),
                    "publie_le": publie,
                    "document": (
                        f"{BASE}/v1/documents/{docs[0]['path']}" if docs else None
                    ),
                }
            )
        return rows

    key = f"amf:dd:index:v1:{','.join(sorted(jetons))}:{since.isoformat()}"
    value, _, _ = await cache.resolve(key, TTL_INDEX, produce)
    return value


async def _detail(row: dict) -> dict:
    lien = row.get("document")
    if not lien:
        return {**row, **parse(""), "lisible": False}

    async def produce():
        try:
            return parse(await asyncio.to_thread(_get_text, lien))
        except Exception:  # noqa: BLE001
            return None

    key = f"amf:dd:doc:v1:{row.get('id')}"
    value, _, _ = await cache.resolve(key, TTL_DOCUMENT, produce)
    if value is None:
        return {**row, **parse(""), "lisible": False}
    return {**row, **value, "lisible": True}


async def insiders(entries: list[tuple[str, str]], days: int = 120) -> dict:
    """Déclarations de dirigeants sur ces valeurs.

    ``entries`` associe un symbole à la raison sociale telle que l'AMF la
    connaît. La correspondance passe par le nom : la BDIF ne connaît pas les
    tickers Yahoo.
    """
    since = dt.date.today() - dt.timedelta(days=days)
    couvertes: list[str] = []
    lignes: list[dict] = []

    async def pour(symbole: str, nom: str) -> list[dict]:
        jetons = await _jetons(nom)
        if not jetons:
            return []
        couvertes.append(symbole.upper())
        rows = await _index(jetons, since)
        return [{**r, "symbol": symbole.upper()} for r in rows]

    groupes = await asyncio.gather(
        *(pour(s, n) for s, n in entries if n), return_exceptions=True
    )
    for groupe in groupes:
        if isinstance(groupe, list):
            lignes.extend(groupe)

    semaphore = asyncio.Semaphore(4)

    async def detail(row: dict) -> dict:
        async with semaphore:
            return await _detail(row)

    results = await asyncio.gather(
        *(detail(r) for r in lignes[:MAX_DOCUMENTS]), return_exceptions=True
    )
    kept = [r for r in results if isinstance(r, dict)]
    kept.sort(
        key=lambda r: (r.get("transaction_le") or r.get("publie_le") or ""), reverse=True
    )
    return {
        "insiders": kept,
        "covered": sorted(set(couvertes)),
        "since": since.isoformat(),
    }


__all__ = ["insiders", "parse", "MAX_DOCUMENTS"]
