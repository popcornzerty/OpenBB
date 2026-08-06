# Brancher une source payante

Le terminal fonctionne **intégralement sans aucune clé**. Ce document décrit ce
qu'une clé lève, et comment la poser le jour venu.

## Ce que la source gratuite plafonne

Yahoo, via `yfinance`, couvre sans clé les quinze places européennes visées :
cotations, historique, états financiers, dividendes, profils. Deux limites
subsistent, et elles sont visibles dans l'écran Valorisation.

**Quatre exercices publiés.** OpenBB plafonne `limit` à 5 pour yfinance, et le
cinquième exercice remonté est vide — réduit à sa date de clôture. La
profondeur réelle est donc de quatre exercices, ce qui se répercute sur :

- les multiples médians de la courbe de juste valeur, calculés sur un
  échantillon d'autant plus sensible à un exercice atypique ;
- la moyenne historique du PER, qui ne porte que sur la période adossée à des
  comptes publiés — environ 3,3 ans, contre 5 ans de graphique.

**Deux exercices estimés, sur deux agrégats.** Le consensus relayé par Yahoo se
limite au chiffre d'affaires et au bénéfice par action, sur l'exercice en cours
et le suivant. Les lignes EBITDA, résultat d'exploitation, flux disponible,
dette nette et capitaux propres restent donc vides dans les colonnes estimées,
ainsi que tous les multiples qui en dépendent.

Une exception : le **dividende du premier exercice estimé** est renseigné à
partir du montant indicatif annoncé par la société. Ce n'est pas un consensus
d'analystes, et l'interface le signale. Les exercices suivants restent vides.

## Fournisseurs utilisables

`openbb-fmp` et `openbb-intrinio` sont **déjà installés** dans l'environnement.
Aucune dépendance à ajouter.

| Fournisseur | Bénéfice | EBITDA | Chiffre d'affaires | PER | États financiers |
|---|---|---|---|---|---|
| Intrinio | oui | oui | oui | oui | approfondis |
| FMP | oui | oui | — | — | approfondis |

Intrinio est retenu en priorité s'il est configuré : il couvre `forward_sales`
et `forward_pe` là où FMP s'arrête au bénéfice et à l'EBITDA.

## Poser la clé

Dans `terminal/backend/.env` :

```
PEATERM_INTRINIO_API_KEY=votre_cle
```

ou

```
PEATERM_FMP_API_KEY=votre_cle
```

Puis redémarrer le backend. Rien d'autre à modifier.

Réglages associés, tous optionnels :

```
PEATERM_PREMIUM_STATEMENT_LIMIT=10   # exercices demandés (défaut : 10)
PEATERM_VALUATION_WINDOW_YEARS=10    # fenêtre des multiples médians
PEATERM_VALUATION_DISPLAY_YEARS=10   # années affichées
```

## Ce qui se produit alors, sans autre intervention

1. **Les états financiers** passent au fournisseur payant, avec la profondeur
   demandée. `settings.statement_limit` remplace le plafond de 5.
2. **Le consensus s'élargit** : `estimates.consensus()` interroge
   `forward_eps`, `forward_ebitda` et, avec Intrinio, `forward_sales`, puis
   fusionne le résultat avec le consensus gratuit.
3. **Les tableaux se remplissent seuls.** `tables.build()` lit les clés
   `ebitda`, `ebit`, `revenue`, `dividend`, `free_cash_flow`, `net_debt`,
   `equity` et `shares` de chaque exercice estimé. Elles sont absentes
   aujourd'hui, présentes demain : aucune ligne de rendu à modifier.
4. **La fenêtre de valorisation** s'étend si vous relevez
   `VALUATION_WINDOW_YEARS`, ce qui allonge d'autant la moyenne historique du
   PER.

## Deux garde-fous

**L'ancrage des exercices reste celui de la source gratuite.** C'est lui qui a
été vérifié contre les comptes publiés, y compris sur les exercices décalés —
Alstom clôture en mars. Le consensus payant n'apporte que des agrégats
supplémentaires et des exercices plus lointains ; sur les champs communs, le
gratuit prime. Voir `_merge_premium` dans `app/providers/estimates.py`.

**Une défaillance du fournisseur payant ne fait rien perdre.** Elle renvoie une
liste vide, et l'appelant retombe sur le consensus gratuit. Une clé expirée
dégrade le tableau, elle ne le casse pas.

## Reconstruire l'univers après le branchement

L'instantané `data/universe_eu.csv` porte les taux de distribution et verdicts
de sûreté calculés au moment de sa génération. Après avoir posé une clé :

```bash
python scripts/build_universe.py --concurrency 6
```

## Vérifier que la clé est prise en compte

```bash
python -c "from app.settings import settings; print(settings.premium_provider, settings.statement_limit)"
```

Sans clé : `None 5`. Avec Intrinio : `intrinio 10`.
