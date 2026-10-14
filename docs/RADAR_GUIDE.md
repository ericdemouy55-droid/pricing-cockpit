# Market Price Radar — mise en service

## Démonstration

Ouvrir Market Price Radar. Dans Collecte & sources, cliquer **Charger un pilote fictif de 200 références**, puis **Charger un historique simulé (4 dates)**. Les observations sont explicitement simulées à J−30, J−7, J−1 et J. Les jours intermédiaires sont vides sur le graphique. Aucune enseigne n’est interrogée et les données de la session ne constituent pas un historique durable de production.

## Catalogue réel et paramètres

1. Importer les BF dans Imports & rapprochement, en production authentifiée. Ajouter si possible profil, XL, runflat, homologation et type de véhicule ; largeur/série/diamètre sont conservés dans la dimension normalisée.
2. Dans Catalogue & paramètres, choisir automatiquement ou manuellement jusqu’à 200 EAN valides et uniques. Le compteur affiche le nombre réellement sélectionné. Un EAN à clé invalide ou associé à plusieurs lignes BF est exclu.
3. Préciser la zone et les identifiants de centre effectivement fournis par les sources. Un centre vide ne contribue pas au prix marché. Un tarif national doit être explicitement identifié comme tel par la source.
4. Choisir la médiane par défaut, sept jours de fraîcheur et l’exclusion des promotions. Activer l’alimentation du scénario de travail après contrôle des données.

## Fichier d’observations

Télécharger le modèle CSV/Excel dans Collecte & sources. Les en-têtes sont en snake_case et conservés tels quels. Un fichier représente une enseigne et peut contenir plusieurs dates. Confirmer la provenance autorisée et en donner une référence avant import. En démo, les fichiers doivent contenir exclusivement des données fictives.

- `ean` : 13 chiffres, clé de contrôle valide. À défaut, marque + référence fabricant ou identité technique complète.
- `brand`, `ref`, `profile`, `dimension`, `load`, `speed`, `season`, `xl`, `runflat`, `homologation` : attributs permettant de contrôler l’identité. `xl` et `runflat` : oui/non ou true/false.
- `price` : prix effectivement affiché, positif ; `price_type` : HT ou TTC ; `currency` : EUR ; `tax_rate` : taux en pourcentage, par exemple 20 lorsque ce taux s’applique. Le taux est obligatoire pour TTC.
- `nature` : pneu_seul. `mounting_included`, `delivery_included`, `member_only`, `conditional_price` doivent être explicitement faux/non. Un prix avec prestation ou condition ne contribue pas au marché.
- `promotion` : vrai/faux ; si vrai, renseigner `promotion_conditions`. `usual_price` permet de contrôler une réduction non déclarée. Montage/livraison affichés séparément peuvent être conservés dans `mounting_fee`/`delivery_fee`.
- `observed_at` : date/heure ISO 8601 avec fuseau, par exemple `2026-10-14T10:00:00+02:00`. Aucune date de relevé manquante n’est inventée.
- `url` : fiche/source HTTPS ; `zone` et `center` : périmètre exact ; `availability` : disponibilité connue, sinon vide.

Un EAN incohérent avec les caractéristiques, une identité ambiguë ou un prix non comparable est rejeté. Un rapprochement technique complet ou une variation excessive passe en attente de validation avec justification. L’acceptation et le rejet sont enregistrés séparément de l’observation d’origine. Une fiche modifiée invalide la validation mémorisée. Un fichier refusé ne remplace jamais le référentiel externe ou les versions existantes.

## PostgreSQL et collecte quotidienne

Exécuter `schema_postgres.sql` dans la base privée existante ou utiliser `python -m eurotyre.radar.cli --migrate` après avoir configuré `RADAR_DATABASE_URL`. La migration ajoute les tables Radar sans supprimer les données existantes. L’interface et l’ordonnanceur doivent utiliser la même base et le même nom d’espace.

Renseigner chaque source autorisée dans les Secrets Streamlit `[radar_sources."Norauto"]`, `[radar_sources."Euromaster"]`, `[radar_sources."Feu Vert"]`, `[radar_sources."First Stop"]`, ou dans le secret GitHub `RADAR_SOURCES_JSON` pour l’ordonnanceur. Une source utilise ce contrat (valeurs à remplacer par une autorisation effective) :

```json
{
  "Norauto": {
    "approved": false,
    "authorization_reference": "",
    "approved_by": "",
    "approved_until": "",
    "url": "",
    "allowed_hosts": [],
    "format": "json",
    "user_agent": "Eurotyre-Market-Price-Radar/1.0",
    "token": ""
  }
}
```

Le flux doit fournir une liste d’observations conforme au modèle, ou un objet JSON contenant `observations`. Le connecteur effectue une seule requête par flux et par exécution, sans redirection ni tentative de contourner un refus. Un token partenaire peut être fourni dans les secrets ; aucun token n’est sauvegardé dans le code, les observations ou les rapports.

Le workflow est installé sur la branche par défaut pour que GitHub puisse lancer le cron et les déclenchements manuels. Il extrait le code de `eurotyre-streamlit-v1`. Définir les secrets `RADAR_DATABASE_URL`, `RADAR_SOURCES_JSON`, la variable facultative `RADAR_WORKSPACE`, puis mettre `RADAR_ENABLED=true` après les tests réels. Le job reste désactivé tant que cette variable n’est pas activée.

Heure proposée : 02:30 UTC (03:30 heure de Paris en hiver, 04:30 en été), modifiable dans le champ cron du workflow. GitHub Actions peut retarder ou suspendre des exécutions ; cet ordonnanceur ne garantit pas un horaire à la minute. Un ordonnanceur serveur peut appeler le même CLI. Le bouton de l’interface permet également une collecte manuelle. L’interface peut rester fermée.

Chaque exécution conserve son rapport dans PostgreSQL. Les erreurs d’une enseigne n’arrêtent pas les autres. Les observations valides, douteuses et absentes sont historisées ; les données de prix restent hors du dépôt et des artefacts Actions.

## Référence de marché et diffusion

Une enseigne compte au plus une fois par EAN et centre choisi. Le prix retenu est la médiane des prix HT validés récents ; moyenne/minimum/maximum sont disponibles. Les promotions sont paramétrables. À défaut de prix concurrent, un prix externe unique, cohérent et daté de moins de sept jours peut servir de repli ; sa source est affichée. Aucune valeur absente ne devient zéro.

La remise BF informative est `(1 − marché HT / BF HT) × 100`. La ligne Marché de la grille reste une moyenne par marque/saison/diamètre. Une remise saisie calcule `BF HT × (1 − remise/100)`. Une cellule vide s’aligne exactement sur le marché valide propre à chaque EAN ; la remise implicite est calculée avant arrondi. L’export affiche cette remise à deux décimales.

Les relevés peuvent modifier le scénario de travail mais aucune version validée/publiée. Créer un nouveau brouillon capture les prix et leurs sources ; résoudre les anomalies, valider et publier restent des actions explicites. Le format de l’export tarifaire principal conserve ses cinq colonnes. L’export concurrentiel complémentaire contient les quatre prix, le marché, Eurotyre, l’écart, la date, la source et la qualité.
