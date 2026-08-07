"""Franchissements de seuils déclarés à l'AMF.

Source : l'API ouverte info-financière (DILA/AMF), sans clé, licence ouverte,
mise à jour quotidienne. Elle indexe les documents réglementés des sociétés
cotées françaises ; les franchissements y forment un sous-type à part.

**Le nom du déclarant n'est pas dans les métadonnées.** Il figure dans le PDF,
qu'il faut donc ouvrir et lire. C'est le prix à payer pour savoir *qui* a
bougé, et sans cette information l'alerte n'apprendrait rien : « un
institutionnel a franchi 5 % sur Valeo » n'a pas la même portée selon qu'il
s'agit de Goldman Sachs ou d'un fonds activiste.

Ce que cette source ne couvre pas, et qu'aucune autre source gratuite
vérifiée ne fournit aujourd'hui :

- **les transactions de dirigeants** (article 19 MAR). L'AMF les publie sur
  son site mais elles sont absentes de ce flux, et le seul miroir structuré
  connu — lestransactions.fr — ne répond plus ;
- **les mouvements ordinaires**. Seuls les franchissements de seuils légaux
  (5 %, 10 %, 15 %, 20 %, 25 %, 30 %, 50 %, 66 %, 90 %, 95 %) sont déclarés.
  Un gérant qui passe de 1 % à 3 % reste invisible.
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

API = (
    "https://www.info-financiere.gouv.fr/api/explore/v2.0"
    "/catalog/datasets/flux-amf-new-prod/records"
)
SUBTYPE = "Décision de franchissement de seuil"
USER_AGENT = "terminal-pea/0.1 (+usage personnel)"

#: L'index bouge une fois par jour ; le relire plus souvent n'apporte rien.
TTL_INDEX = 6 * 3600

#: Un document publié ne change plus. Son contenu analysé se garde longtemps.
TTL_DOCUMENT = 30 * 86400

#: Au-delà, on ne télécharge plus : une alerte de plusieurs mois n'en est plus
#: une, et chaque PDF coûte un appel réseau.
MAX_DOCUMENTS = 40


_PHRASE = re.compile(
    r"[Pp]ar\s+(?:un\s+)?(?:courrier|courriel|t[ée]l[ée]copie|d[ée]claration)"
    r"[^,]{0,80},\s*(?P<suite>.{0,400})",
    re.DOTALL,
)

#: Qualification juridique qui précède le nom. « la société » domine, mais les
#: personnes physiques déclarent aussi — et ce sont elles qui signalent un
#: mouvement d'actionnaire familial ou de dirigeant.
_QUALIFIER = re.compile(
    r"^(?P<forme>la\s+soci[ée]t[ée]|le\s+fonds|la\s+compagnie|l[ae]\s+groupe"
    r"|M\.|Mme|MM\.|Monsieur|Madame)\s+",
    re.IGNORECASE,
)

_SENS = re.compile(r"franchi\w*\s+en\s+(?P<sens>hausse|baisse)", re.IGNORECASE)
_SEUIL = re.compile(r"seuils?\s+de\s+(?P<seuil>\d{1,2}(?:[,.]\d+)?)\s*%", re.IGNORECASE)
_NATURE = re.compile(r"seuils?\s+de\s+[\d,.]+\s*%\s+(?P<nature>du\s+capital|des\s+droits\s+de\s+vote)", re.IGNORECASE)
_DATE_FR = re.compile(r"franchi\w*\s+en\s+(?:hausse|baisse)\s*,?\s*le\s+(?P<jour>\d{1,2}\s+\w+\s+20\d\d)")

_MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

#: Indices d'une personne physique dans la forme déclarée.
_PERSONNES = ("m.", "mme", "mm.", "monsieur", "madame")


def _iso_date(texte: str) -> str | None:
    """Convertit « 23 juillet 2026 » en date ISO."""
    parts = texte.lower().split()
    if len(parts) != 3 or parts[1] not in _MOIS:
        return None
    try:
        return dt.date(int(parts[2]), _MOIS[parts[1]], int(parts[0])).isoformat()
    except ValueError:
        return None


def _declarant(texte: str) -> tuple[str | None, str]:
    """Nom du déclarant et sa nature, lus dans le corps de la déclaration.

    Renvoie ``(nom, nature)`` où la nature vaut ``"morale"``, ``"physique"``
    ou ``"inconnue"``. La distinction compte : une personne physique qui
    franchit un seuil est le plus souvent un fondateur ou un actionnaire
    familial, ce qui ne se lit pas comme l'arbitrage d'un gérant.
    """
    match = _PHRASE.search(texte)
    if not match:
        return None, "inconnue"
    suite = match.group("suite").lstrip()

    forme = _QUALIFIER.match(suite)
    nature = "inconnue"
    if forme:
        nature = "physique" if forme.group("forme").lower() in _PERSONNES else "morale"
        suite = suite[forme.end() :]

    # Le nom court jusqu'à l'adresse, ouverte par une parenthèse. Il peut
    # contenir des virgules — « The Goldman Sachs Group, Inc » — ce qui
    # interdit de s'arrêter au premier séparateur venu.
    coupe = suite.find("(")
    nom = suite[:coupe] if 0 < coupe < 120 else suite[:90]
    nom = re.sub(r"\d+$", "", nom.strip(" ,;:"))  # appel de note éventuel
    nom = re.sub(r"\s+", " ", nom).strip(" ,;:")

    # La qualification se poursuit souvent en toutes lettres — « la société
    # par actions simplifiée Rock Investment », « la société anonyme de droit
    # belge SITAM Belgique ». Ces descripteurs sont en minuscules là où la
    # raison sociale commence par une majuscule : on élague jusqu'à elle.
    mots = nom.split()
    while len(mots) > 1 and mots[0][:1].islower():
        mots = mots[1:]
    if mots:
        nom = " ".join(mots)

    if not nom or len(nom) < 3:
        return None, nature
    return nom, nature


def parse(texte: str) -> dict:
    """Extrait ce qui fait l'intérêt d'un avis de franchissement."""
    nom, nature = _declarant(texte)
    sens = _SENS.search(texte)
    seuil = _SEUIL.search(texte)
    nature_seuil = _NATURE.search(texte)
    quand = _DATE_FR.search(texte)
    return {
        "declarant": nom,
        "declarant_nature": nature,
        "sens": sens.group("sens").lower() if sens else None,
        "seuil": float(seuil.group("seuil").replace(",", ".")) if seuil else None,
        "seuil_nature": (
            "droits de vote"
            if nature_seuil and "droits" in nature_seuil.group("nature").lower()
            else "capital"
            if nature_seuil
            else None
        ),
        "franchi_le": _iso_date(quand.group("jour")) if quand else None,
    }


def _fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str) -> str:
    import pypdf

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    pages = pypdf.PdfReader(io.BytesIO(raw)).pages
    return " ".join(" ".join((page.extract_text() or "").split()) for page in pages)


#: Plafond imposé par l'API : au-delà, elle refuse la requête.
PAGE_SIZE = 100

#: Nombre de pages parcourues au plus. Six mois de franchissements sur toute
#: la cote française tiennent largement dans cette borne.
MAX_PAGES = 6


async def _index(since: dt.date) -> list[dict]:
    """Tous les avis de franchissement publiés depuis ``since``.

    Le filtrage sur les valeurs suivies se fait ensuite, en mémoire, à partir
    de la raison sociale que porte l'index : demander à l'API une liste de
    codes ISIN supposerait de les connaître, ce qui n'est pas le cas.
    """
    where = (
        f"sous_type_d_information='{SUBTYPE}' "
        f"AND uin_dat_amf >= date'{since.isoformat()}'"
    )
    base = f"{API}?where={urllib.parse.quote(where)}&order_by=-uin_dat_amf"

    async def produce():
        rows: list[dict] = []
        for page in range(MAX_PAGES):
            url = f"{base}&limit={PAGE_SIZE}&offset={page * PAGE_SIZE}"
            try:
                payload = await asyncio.to_thread(_fetch_json, url)
            except Exception:  # noqa: BLE001
                break
            records = payload.get("records", [])
            for record in records:
                fields = record.get("record", {}).get("fields", record)
                rows.append(
                    {
                        "id": fields.get("uin_idt_uin"),
                        "isin": fields.get("identificationsociete_iso_cd_isi"),
                        "societe": fields.get("identificationsociete_iso_nom_soc"),
                        "publie_le": (fields.get("uin_dat_amf") or "")[:10],
                        "titre": fields.get("informationdeposee_inf_tit_inf"),
                        "document": fields.get("url_de_recuperation"),
                    }
                )
            if len(records) < PAGE_SIZE:
                break
        return rows

    key = f"amf:index:v3:{since.isoformat()}"
    value, _, _ = await cache.resolve(key, TTL_INDEX, produce)
    return value


async def _detail(row: dict) -> dict:
    """Complète un avis par la lecture de son PDF."""
    link = row.get("document") or ""
    if not link.endswith(".pdf"):
        return {**row, **parse(""), "lisible": False}

    async def produce():
        try:
            texte = await asyncio.to_thread(_fetch_text, link)
        except Exception:  # noqa: BLE001
            return None
        return parse(texte)

    key = f"amf:doc:v1:{row.get('id')}"
    value, _, _ = await cache.resolve(key, TTL_DOCUMENT, produce)
    if value is None:
        # Certains avis sont des images sans couche texte : on les garde dans
        # la liste, avec leur lien, plutôt que de les faire disparaître.
        return {**row, **parse(""), "lisible": False}
    return {**row, **value, "lisible": True}


async def crossings(entries: list[tuple[str, str]], days: int = 120) -> dict:
    """Franchissements de seuils récents sur ces valeurs, déclarant nommé.

    ``entries`` associe un symbole à la raison sociale telle que l'AMF la
    connaît. Le rattachement se fait sur ce nom, présent dans l'index : passer
    par une résolution ISIN → ticker imposait une centaine d'interrogations
    d'un service tiers pour chaque consultation, au prix de plusieurs minutes
    d'attente.

    Les PDF ne sont ouverts que pour les avis retenus : chaque document est un
    appel réseau, et l'AMF n'est pas un service qu'on martèle.
    """
    par_nom = {nom.strip().upper(): symbole.upper() for symbole, nom in entries if nom}
    since = dt.date.today() - dt.timedelta(days=days)
    rows = await _index(since)
    if not rows:
        return {"crossings": [], "covered": [], "scanned": 0, "since": since.isoformat()}

    retenus = []
    couvertes: set[str] = set()
    for row in rows:
        nom = (row.get("societe") or "").strip().upper()
        symbole = par_nom.get(nom)
        if symbole:
            couvertes.add(symbole)
            retenus.append({**row, "symbol": symbole})

    semaphore = asyncio.Semaphore(4)

    async def detail(row: dict) -> dict:
        async with semaphore:
            return await _detail(row)

    results = await asyncio.gather(
        *(detail(r) for r in retenus[:MAX_DOCUMENTS]), return_exceptions=True
    )
    kept = [r for r in results if isinstance(r, dict)]
    kept.sort(key=lambda r: (r.get("franchi_le") or r.get("publie_le") or ""), reverse=True)

    return {
        "crossings": kept,
        "covered": sorted(couvertes),
        "scanned": len(rows),
        "since": since.isoformat(),
    }


__all__ = ["crossings", "parse", "MAX_DOCUMENTS"]
