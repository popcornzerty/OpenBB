/** Glossaire des indicateurs affichés par le terminal.
 *
 *  Le périmètre est délibérément technique : les notions générales — PEA,
 *  action, cours, ticker, indice, secteur, position, PRU, plus-value — en sont
 *  exclues. Elles se comprennent sans le terminal ; ce qui mérite une fiche,
 *  c'est ce que l'écran affiche sans l'expliquer.
 *
 *  Les mises en garde ne sont pas décoratives : un rendement élevé ou une
 *  décote apparente se lisent mal sans elles. Elles restent attachées à la
 *  fiche plutôt qu'à l'écran, pour ne pas dépendre de l'endroit où le terme
 *  est rencontré.
 */

export type GlossaryCategory =
  | "dividendes"
  | "fondamentaux"
  | "valorisation"
  | "risque"
  | "donnees";

export type GlossaryLocation = "screener" | "societe" | "valorisation";

export interface GlossaryEntry {
  id: string;
  term: string;
  /** Sigles et formulations alternatives, tous recherchables. */
  aliases?: string[];
  category: GlossaryCategory;
  definition: string;
  formula?: string;
  locations: GlossaryLocation[];
  caution?: string;
}

export const CATEGORY_LABELS: Record<GlossaryCategory, string> = {
  dividendes: "Dividendes",
  fondamentaux: "Fondamentaux",
  valorisation: "Valorisation",
  risque: "Risque et qualité",
  donnees: "Données",
};

export const LOCATION_LABELS: Record<GlossaryLocation, string> = {
  screener: "Screener PEA",
  societe: "Société",
  valorisation: "Valorisation",
};

export const glossaryEntries: GlossaryEntry[] = [
  {
    id: "rendement",
    term: "Rendement",
    aliases: ["rendement du dividende", "dividend yield"],
    category: "dividendes",
    definition:
      "Part du cours de l'action potentiellement reçue en dividendes sur une année. Un rendement élevé peut aussi refléter un cours en baisse ou un dividende difficile à maintenir.",
    formula: "Dividende annuel par action / cours de l'action",
    locations: ["screener", "societe", "valorisation"],
    caution: "À lire avec le taux de distribution et le flux de trésorerie libre.",
  },
  {
    id: "taux-distribution",
    term: "Taux de distribution",
    aliases: ["payout ratio"],
    category: "dividendes",
    definition:
      "Part du bénéfice net versée aux actionnaires sous forme de dividendes. Un taux durablement très élevé peut laisser peu de marge pour investir ou absorber une baisse des résultats.",
    formula: "Dividendes versés / résultat net",
    locations: ["screener", "valorisation"],
  },
  {
    id: "croissance-dividende",
    term: "Croissance du dividende",
    aliases: ["croissance annualisée du dividende"],
    category: "dividendes",
    definition:
      "Rythme moyen auquel le dividende par action a progressé sur la période observée. Elle décrit le passé et ne garantit pas les futurs versements.",
    locations: ["screener", "valorisation"],
  },
  {
    id: "flux-libre-absorbe",
    term: "Flux libre absorbé",
    aliases: ["couverture du dividende par le FCF"],
    category: "dividendes",
    definition:
      "Part du flux de trésorerie libre utilisée pour financer le dividende. Plus cette part est élevée, moins l'entreprise conserve de trésorerie pour réduire sa dette ou investir.",
    formula: "Dividendes versés / flux de trésorerie libre",
    locations: ["screener", "valorisation"],
  },
  {
    id: "surete-dividende",
    term: "Dividende sûr / tendu / non couvert",
    aliases: ["sûreté du dividende"],
    category: "dividendes",
    definition:
      "Indicateur maison de la capacité apparente à financer le dividende avec le bénéfice et le flux de trésorerie libre. « Sûr » indique une couverture confortable ; « tendu », une marge limitée ; « non couvert », un dividende qui dépasse au moins une mesure de couverture.",
    locations: ["screener", "valorisation"],
    caution: "C'est un repère, pas une prévision de baisse ou de maintien du dividende.",
  },
  {
    id: "date-detachement",
    term: "Date de détachement estimée",
    aliases: ["ex-date", "date ex-dividende"],
    category: "dividendes",
    definition:
      "Date à partir de laquelle l'achat de l'action ne donne plus droit au prochain dividende. Dans le terminal, elle peut être estimée à partir du calendrier historique.",
    locations: ["screener", "valorisation"],
    caution: "Une date estimée peut changer après les annonces de la société.",
  },
  {
    id: "chiffre-affaires",
    term: "Chiffre d'affaires",
    aliases: ["CA", "revenus", "ventes"],
    category: "fondamentaux",
    definition:
      "Total des ventes réalisées par l'entreprise avant déduction de ses charges. Sa croissance montre l'évolution de l'activité, mais pas directement celle du bénéfice.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "ebitda",
    term: "EBITDA",
    aliases: ["excédent brut d'exploitation"],
    category: "fondamentaux",
    definition:
      "Mesure du résultat généré par l'activité avant intérêts, impôts, amortissements et dépréciations. Elle facilite la comparaison d'entreprises, mais ne représente pas la trésorerie réellement disponible.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "resultat-operationnel",
    term: "Résultat opérationnel",
    aliases: ["EBIT", "résultat d'exploitation"],
    category: "fondamentaux",
    definition:
      "Profit issu de l'activité courante de l'entreprise, avant éléments financiers et impôts. Il mesure la rentabilité de l'exploitation.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "resultat-net",
    term: "Résultat net",
    aliases: ["bénéfice net"],
    category: "fondamentaux",
    definition:
      "Bénéfice final après prise en compte de l'activité, de la dette, des impôts et des éléments exceptionnels. C'est la base de plusieurs ratios, dont le PER.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "bpa",
    term: "BPA / BNPA dilué",
    aliases: ["bénéfice par action", "EPS"],
    category: "fondamentaux",
    definition:
      "Part du résultat net attribuable à une action. La version « diluée » tient compte des titres potentiellement créés, comme les options ou actions attribuées.",
    formula: "Résultat net attribuable aux actionnaires / nombre moyen d'actions dilué",
    locations: ["societe", "valorisation"],
  },
  {
    id: "marge-brute",
    term: "Marge brute",
    category: "fondamentaux",
    definition:
      "Part du chiffre d'affaires restant après les coûts directement nécessaires pour produire ou acheter les biens et services vendus.",
    formula: "(Chiffre d'affaires − coût des ventes) / chiffre d'affaires",
    locations: ["societe"],
  },
  {
    id: "marge-operationnelle",
    term: "Marge opérationnelle",
    aliases: ["marge d'exploitation"],
    category: "fondamentaux",
    definition:
      "Part du chiffre d'affaires conservée en résultat opérationnel. Elle donne une idée de l'efficacité de l'activité principale.",
    formula: "Résultat opérationnel / chiffre d'affaires",
    locations: ["societe", "valorisation"],
  },
  {
    id: "marge-nette",
    term: "Marge nette",
    category: "fondamentaux",
    definition:
      "Part du chiffre d'affaires qui devient un bénéfice net après toutes les charges, intérêts et impôts.",
    formula: "Résultat net / chiffre d'affaires",
    locations: ["societe", "valorisation"],
  },
  {
    id: "flux-tresorerie-libre",
    term: "Flux de trésorerie libre",
    aliases: ["FCF", "free cash flow", "flux disponible"],
    category: "fondamentaux",
    definition:
      "Trésorerie restant après les dépenses nécessaires au fonctionnement et aux investissements. Elle peut servir à rembourser la dette, financer des acquisitions, racheter des actions ou verser des dividendes.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "dette-nette",
    term: "Dette nette",
    aliases: ["net debt"],
    category: "fondamentaux",
    definition:
      "Dette financière totale diminuée de la trésorerie disponible. Elle mesure l'endettement restant si l'entreprise utilisait immédiatement sa trésorerie pour rembourser ses dettes.",
    formula: "Dette financière − trésorerie et équivalents",
    locations: ["societe", "valorisation"],
  },
  {
    id: "capitaux-propres",
    term: "Capitaux propres",
    aliases: ["actif net comptable"],
    category: "fondamentaux",
    definition:
      "Valeur comptable restant aux actionnaires après déduction de l'ensemble des dettes. Elle ne correspond pas nécessairement à la valeur de marché de l'entreprise.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "ratio-liquidite",
    term: "Ratio de liquidité",
    aliases: ["current ratio"],
    category: "fondamentaux",
    definition:
      "Indicateur de la capacité de l'entreprise à couvrir ses obligations à court terme avec ses actifs à court terme.",
    formula: "Actif courant / passif courant",
    locations: ["societe", "valorisation"],
  },
  {
    id: "capitalisation",
    term: "Capitalisation boursière",
    aliases: ["capitalisation", "market cap"],
    category: "valorisation",
    definition:
      "Valeur totale des actions d'une entreprise en Bourse. Elle évolue en permanence avec le cours de l'action.",
    formula: "Cours de l'action × nombre d'actions",
    locations: ["screener", "societe", "valorisation"],
  },
  {
    id: "valeur-entreprise",
    term: "Valeur d'entreprise",
    aliases: ["VE", "enterprise value"],
    category: "valorisation",
    definition:
      "Valeur théorique de l'activité pour un acquéreur : elle combine la valeur des actions et l'endettement net. Elle permet de comparer des entreprises financées différemment.",
    formula: "Capitalisation boursière + dette nette",
    locations: ["valorisation"],
  },
  {
    id: "per",
    term: "PER",
    aliases: ["Price Earnings Ratio", "cours/bénéfice"],
    category: "valorisation",
    definition:
      "Rapport entre le cours de l'action et son bénéfice par action. Il exprime le prix payé par le marché pour une unité de bénéfice.",
    formula: "Cours de l'action / BPA",
    locations: ["societe", "valorisation"],
    caution:
      "À comparer avec l'historique de la société, ses perspectives et des entreprises comparables.",
  },
  {
    id: "per-estime",
    term: "PER estimé",
    aliases: ["forward PER"],
    category: "valorisation",
    definition:
      "PER calculé à partir d'un bénéfice attendu sur un exercice futur. Il dépend donc des prévisions d'analystes, qui peuvent être révisées.",
    formula: "Cours de l'action / BPA estimé",
    locations: ["societe", "valorisation"],
  },
  {
    id: "ps",
    term: "Capitalisation / chiffre d'affaires",
    aliases: ["P/S", "Price to Sales"],
    category: "valorisation",
    definition:
      "Rapport entre la capitalisation boursière et le chiffre d'affaires. Il est particulièrement utile lorsque les bénéfices sont momentanément faibles, mais ignore la rentabilité.",
    formula: "Capitalisation boursière / chiffre d'affaires",
    locations: ["valorisation"],
  },
  {
    id: "pb",
    term: "Capitalisation / capitaux propres",
    aliases: ["P/B", "Price to Book", "cours/actif net"],
    category: "valorisation",
    definition:
      "Rapport entre la valeur boursière et les capitaux propres comptables. Il est souvent plus informatif pour les banques et les assurances que pour les entreprises de croissance.",
    formula: "Capitalisation boursière / capitaux propres",
    locations: ["societe", "valorisation"],
  },
  {
    id: "ve-ebitda",
    term: "VE / EBITDA",
    aliases: ["EV/EBITDA"],
    category: "valorisation",
    definition:
      "Rapport entre la valeur d'entreprise et l'EBITDA. Il compare le prix global de l'entreprise à sa performance opérationnelle avant amortissements, intérêts et impôts.",
    formula: "Valeur d'entreprise / EBITDA",
    locations: ["valorisation"],
  },
  {
    id: "juste-valeur",
    term: "Juste valeur estimée",
    aliases: ["fair value"],
    category: "valorisation",
    definition:
      "Estimation du prix théorique d'une action obtenue à partir du modèle du terminal et de données historiques. Elle constitue un repère d'analyse, pas un objectif de cours ni une recommandation.",
    locations: ["valorisation"],
    caution:
      "Le résultat dépend des données disponibles, de la période retenue et des hypothèses du modèle.",
  },
  {
    id: "prime-decote",
    term: "Prime / décote",
    aliases: ["écart à la juste valeur"],
    category: "valorisation",
    definition:
      "Écart entre le cours actuel et une valeur de référence. Une décote signifie que le cours est inférieur à cette référence ; une prime signifie qu'il est supérieur.",
    formula: "(Cours actuel − valeur de référence) / valeur de référence",
    locations: ["valorisation"],
  },
  {
    id: "consensus",
    term: "Consensus des analystes",
    aliases: ["consensus"],
    category: "valorisation",
    definition:
      "Synthèse des prévisions ou objectifs de cours publiés par plusieurs analystes. Il reflète une opinion de marché à un instant donné, et non une certitude.",
    locations: ["valorisation"],
  },
  {
    id: "objectif-cours",
    term: "Objectif de cours",
    aliases: ["target price"],
    category: "valorisation",
    definition:
      "Prix qu'un analyste estime atteignable sur son horizon d'analyse. L'objectif moyen ou médian agrège plusieurs estimations, qui peuvent diverger fortement.",
    locations: ["valorisation"],
  },
  {
    id: "mediane",
    term: "Médiane",
    category: "valorisation",
    definition:
      "Valeur située au milieu d'une série une fois les données classées. Elle est moins influencée par les valeurs extrêmes que la moyenne.",
    locations: ["valorisation"],
  },
  {
    id: "dispersion",
    term: "Dispersion",
    category: "valorisation",
    definition:
      "Mesure de l'écart entre les différentes valeurs observées. Une dispersion élevée indique des données, des multiples ou des prévisions plus hétérogènes.",
    locations: ["valorisation"],
  },
  {
    id: "fenetre-calcul",
    term: "Fenêtre de calcul",
    aliases: ["période historique"],
    category: "donnees",
    definition:
      "Période de données utilisée pour produire une moyenne, une médiane ou la juste valeur. Une fenêtre courte peut rendre le résultat plus sensible à une année atypique.",
    locations: ["valorisation"],
  },
  {
    id: "roe",
    term: "ROE",
    aliases: ["Return on Equity", "rendement des capitaux propres"],
    category: "risque",
    definition:
      "Mesure de la capacité d'une entreprise à générer un bénéfice avec les capitaux apportés ou conservés par les actionnaires.",
    formula: "Résultat net / capitaux propres moyens",
    locations: ["societe", "valorisation"],
    caution: "Un ROE élevé peut aussi être amplifié par un endettement important.",
  },
  {
    id: "dette-fonds-propres",
    term: "Dette / fonds propres",
    aliases: ["debt to equity"],
    category: "risque",
    definition:
      "Rapport entre l'endettement et les capitaux propres. Il indique le poids relatif de la dette dans le financement de l'entreprise.",
    formula: "Dette totale / capitaux propres",
    locations: ["societe", "valorisation"],
    caution: "Les niveaux habituels diffèrent fortement selon les secteurs.",
  },
  {
    id: "beta",
    term: "Bêta",
    aliases: ["beta"],
    category: "risque",
    definition:
      "Mesure de la sensibilité historique du cours aux variations du marché. Un bêta de 1 indique une évolution historiquement proche du marché ; supérieur à 1, des mouvements généralement plus amples.",
    locations: ["societe"],
    caution: "Le bêta décrit le passé et ne prédit pas les variations futures.",
  },
  {
    id: "note-qualite",
    term: "Note qualité",
    aliases: ["score qualité"],
    category: "risque",
    definition:
      "Score maison fondé sur la rentabilité, la conversion en trésorerie, la solidité financière, la croissance et la stabilité. Il sert à comparer des profils, pas à résumer seul une entreprise.",
    locations: ["valorisation"],
  },
  {
    id: "conversion-cash",
    term: "Conversion en cash",
    aliases: ["conversion en trésorerie"],
    category: "risque",
    definition:
      "Capacité de l'entreprise à transformer son résultat net en flux de trésorerie libre. Une conversion durablement faible peut signaler de forts besoins d'investissement ou de fonds de roulement.",
    formula: "Flux de trésorerie libre / résultat net",
    locations: ["valorisation"],
  },
  {
    id: "stabilite",
    term: "Stabilité",
    category: "risque",
    definition:
      "Régularité historique du chiffre d'affaires et des marges. Dans la note qualité, une faible dispersion des résultats correspond à une meilleure stabilité.",
    locations: ["valorisation"],
  },
  {
    id: "exercice-publie",
    term: "Exercice publié",
    aliases: ["résultats publiés"],
    category: "donnees",
    definition:
      "Année comptable dont les résultats ont été officiellement communiqués par l'entreprise. Ces données sont différentes des estimations d'analystes.",
    locations: ["societe", "valorisation"],
  },
  {
    id: "estimation",
    term: "Estimation (e)",
    aliases: ["2026e", "2027e", "prévision analystes"],
    category: "donnees",
    definition:
      "Donnée attendue pour un exercice futur, identifiée par le suffixe « e ». Elle repose généralement sur le consensus d'analystes et peut évoluer à chaque nouvelle publication.",
    locations: ["valorisation"],
  },
  {
    id: "confiance-faible",
    term: "Confiance faible",
    aliases: ["niveau de confiance"],
    category: "donnees",
    definition:
      "Signal indiquant que l'estimation repose sur peu de données exploitables, une période courte ou des résultats instables. La juste valeur affichée doit alors être interprétée avec prudence.",
    locations: ["valorisation"],
  },
  {
    id: "donnees-historiques-limitees",
    term: "Données historiques limitées",
    aliases: ["profondeur historique"],
    category: "donnees",
    definition:
      "Limitation de la période de comptes ou de cours disponible. Elle réduit la robustesse des moyennes historiques et peut donner plus de poids à une année exceptionnelle.",
    locations: ["societe", "valorisation"],
  },
];

/** Index par identifiant, pour les renvois contextuels. */
export const glossaryById: Record<string, GlossaryEntry> = Object.fromEntries(
  glossaryEntries.map((entry) => [entry.id, entry]),
);

/** Retire accents et casse : « Bêta » doit se trouver en tapant « beta ». */
export function normalize(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/['’]/g, "'");
}

/** Pertinence d'une fiche pour une recherche. Zéro signifie « sans rapport ».
 *
 *  Le classement est indispensable, pas cosmétique : chercher « PER » sans lui
 *  remontait « Croissance du dividende » et « Résultat opérationnel », dont
 *  les définitions contiennent « période » et « opérationnel ». La fiche PER
 *  n'apparaissait nulle part.
 */
function score(entry: GlossaryEntry, needle: string): number {
  const term = normalize(entry.term);
  const aliases = (entry.aliases ?? []).map(normalize);

  if (term === needle || aliases.includes(needle)) return 100;
  if (term.startsWith(needle)) return 80;
  if (aliases.some((alias) => alias.startsWith(needle))) return 70;
  // Un mot entier du terme, pour que « marge » trouve « Marge nette ».
  if (term.split(/[\s/]+/).includes(needle)) return 60;
  if (term.includes(needle)) return 40;
  if (aliases.some((alias) => alias.includes(needle))) return 30;
  // La définition compte en dernier recours : elle rattrape les recherches
  // par intention — « impôt », « trésorerie » — sans jamais primer.
  if (normalize(entry.definition).includes(needle)) return 10;
  return 0;
}

/** Recherche sur le terme, ses alias et sa définition, par pertinence.
 *
 *  Les alias comptent autant que le terme : personne ne cherche « Capitalisation
 *  / capitaux propres », on tape « P/B ». */
export function searchGlossary(query: string): GlossaryEntry[] {
  const needle = normalize(query.trim());
  if (!needle) return glossaryEntries;
  return glossaryEntries
    .map((entry) => ({ entry, poids: score(entry, needle) }))
    .filter((row) => row.poids > 0)
    .sort((a, b) => b.poids - a.poids || a.entry.term.localeCompare(b.entry.term, "fr"))
    .map((row) => row.entry);
}
