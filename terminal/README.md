# Terminal PEA

Terminal d'investissement de bureau centré sur les **actions européennes
éligibles au PEA**, bâti sur [OpenBB](https://github.com/OpenBB-finance/OpenBB).

Backend Python (FastAPI + OpenBB) · frontend React/TypeScript · fenêtre native Tauri.

---

## Ce que fait l'application

| Écran | Contenu |
|---|---|
| **Marché** | Listes de suivi, cotations, bandeau des grands indices européens |
| **Screener PEA** | 377 valeurs européennes, filtre d'éligibilité PEA, pays du siège, secteur, indice, capitalisation |
| **Société** | Profil, verdict PEA justifié, chiffres clés, cours, comptes sur 5 exercices, dividendes, actualités |
| **Valorisation** | Courbe de juste valeur, multiples médians, note de qualité, prolongement 18 mois |

Recherche par **nom, ticker ou ISIN** (`Ctrl` + `K`) — les relevés de brokers
français identifiant les titres par ISIN, `FR0000121014` mène directement à LVMH.

---

## Éligibilité PEA

Est éligible l'action d'une société dont le **siège social** est dans l'Espace
économique européen : UE 27 + Islande, Norvège, Liechtenstein.

Le lieu de cotation n'entre pas en compte, et c'est là que se jouent les cas
piégeux que le terminal traite explicitement :

- **Airbus**, cotée à Paris, siège aux Pays-Bas → **éligible**
- **DSM-Firmenich**, cotée à Amsterdam, société de droit suisse → **non éligible**
- **IAG**, siège opérationnel à Londres mais société de droit espagnol → **éligible**
- **ABB**, cotée à Stockholm, siège suisse → **non éligible**

Quand le pays du siège n'est pas connu, le statut affiché est *indéterminé* —
jamais « éligible » par défaut. Les cas où la donnée du fournisseur diverge du
siège statutaire sont corrigés dans `SEAT_OVERRIDES`
(`backend/app/pea/eligibility.py`), chaque entrée portant sa justification.

---

## Sources de données

Tout fonctionne **sans aucune clé d'API**.

| Donnée | Source |
|---|---|
| Cours, cotations, fondamentaux, dividendes, actualités, indices | Yahoo Finance via OpenBB |
| Recherche par nom / ticker / ISIN | endpoint de recherche Yahoo |
| Taux de change (conversion des capitalisations en euros) | Banque centrale européenne |

Couverture vérifiée sur 15 places : Paris, Amsterdam, Bruxelles, Lisbonne,
XETRA, Francfort, Milan, Madrid, Copenhague, Stockholm, Helsinki, Oslo, Vienne,
Varsovie.

### Deux limites à connaître

1. **Cotations différées d'environ 15 minutes** sur Euronext et XETRA. Aucune
   source gratuite ne diffuse ces places en temps réel. L'horodatage de la
   donnée est affiché.
2. **Cinq exercices de fondamentaux au maximum.** C'est le plafond de la source
   gratuite, pas un choix d'affichage — ce qui limite la fenêtre de valorisation
   à 5 ans au lieu des 10 ans idéaux (voir plus bas).

---

## Valorisation

Pour chaque fondamental — bénéfices, ventes, valeur comptable, flux de
trésorerie — le **multiple médian historique du titre** est appliqué à la donnée
par action correspondante. Les contributions sont combinées avec une pondération
**inversement proportionnelle à la volatilité de chaque multiple** : un multiple
historiquement stable pèse davantage. La courbe est lissée, puis une **prime ou
décote de qualité bornée à ±15 %** est appliquée. Une portion en pointillé
prolonge la courbe sur 18 mois selon sa croissance récente — illustratif, non
prédictif.

Aucun calcul n'utilise une information qui n'était pas encore publique : chaque
exercice n'entre dans la série qu'à partir de sa date de publication estimée.

### Garde-fous ajoutés

Trois défauts sont apparus au banc d'essai et sont corrigés :

- **Multiples écrêtés aux déciles extrêmes.** Un exercice ponctuellement déprimé
  produit un PER de plusieurs centaines qui, sur cinq exercices seulement,
  occupe assez d'observations pour déplacer la médiane elle-même.
- **Composantes couvrant moins de 60 % de la fenêtre écartées.** Une composante
  présente par intermittence affiche mécaniquement une faible dispersion — elle
  n'a pas eu le temps de varier — et capterait donc un poids démesuré.
- **Flux de trésorerie ignoré pour les sociétés financières.** Chez une banque,
  les flux d'exploitation sont dominés par les variations de bilan : le « FCF »
  qui en résulte ne mesure aucune création de valeur.

### Note de qualité

Score **maison**, calculé sur des seuils absolus : rentabilité, conversion en
cash, solidité financière, croissance, stabilité. Chaque axe est affiché avec ce
qui l'a produit. **Ce n'est pas la note Q de Baggr**, qui est propriétaire.

Le choix de seuils absolus plutôt que d'un classement face aux pairs est
délibéré : un score relatif ferait bouger la juste valeur d'une société chaque
fois que ses concurrents bougent, alors que ses propres comptes n'ont pas changé.

### Porter la fenêtre à 10 ans

`valuation_window_years` dans `backend/app/settings.py`, ou la variable
d'environnement `PEATERM_VALUATION_WINDOW_YEARS`. Le moteur suivra, mais la
profondeur réelle restera limitée par la source : il faut y brancher un
fournisseur payant (EODHD, FMP Premium, Intrinio) pour dépasser 5 exercices.

---

## Installation et lancement

### Prérequis

- Python ≥ 3.10 (testé sur 3.14)
- Node.js ≥ 18 (testé sur 24)
- Rust stable + build tools MSVC — pour la fenêtre native uniquement

### Backend

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt
```

Puis construire l'univers européen — chaque ticker est réellement interrogé,
ceux qui ne répondent pas sont écartés :

```bash
cd backend; python scripts/build_universe.py
```

Lancer le serveur :

```bash
cd backend; python -m uvicorn app.main:app --port 8801
```

### Frontend en développement

```bash
cd frontend; npm install; npm run dev
```

Interface sur <http://localhost:5180> ; les appels `/api` sont relayés vers le
backend.

### Fenêtre native

```bash
cd frontend; npm run tauri dev
```

Construire l'installeur Windows :

```bash
cd frontend; npm run tauri build
```

La coquille Tauri démarre le backend au lancement et l'arrête à la fermeture.
Elle cherche l'interpréteur Python dans l'environnement virtuel du dépôt ;
`PEATERM_PYTHON` permet d'en imposer un autre.

---

## Tests

```bash
cd backend; python -m pytest
```

Couvrent l'éligibilité PEA (cas où siège et cotation divergent, pays inconnu,
exceptions) et le moteur de valorisation (pondération inverse-volatilité,
bornage de la prime, exclusion des fondamentaux négatifs, garde-fous).

---

## Organisation

```
terminal-pea/
├── backend/
│   ├── app/
│   │   ├── pea/            éligibilité PEA, univers européen
│   │   ├── providers/      OpenBB, recherche Yahoo, taux BCE
│   │   ├── valuation/      séries par action, multiples, qualité, juste valeur
│   │   └── routers/        market, search, company, screener, valuation, watchlists
│   ├── data/               seed d'indices + univers validé
│   ├── scripts/            construction de l'univers
│   └── tests/
└── frontend/
    ├── src/
    │   ├── panels/         Marché, Screener, Société, Valorisation
    │   ├── components/     graphique, barre de commande, bandeau d'indices, badge PEA
    │   └── lib/            client d'API, formatage francophone
    └── src-tauri/          coquille native
```

---

## Avertissement

Cet outil produit des estimations à partir de données publiques gratuites et
différées. Il ne constitue pas un conseil en investissement. L'éligibilité PEA
affichée est une aide à la décision : la seule source qui fait foi est votre
intermédiaire financier.
