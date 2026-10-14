# Audit et intégration au Pricing Manager

Projet repris : `ericdemouy55-droid/pricing-cockpit`, branche `eurotyre-streamlit-v1`, point de départ `7e7a7516a9690d8c193e4ab6dca6a349bfb4bc4a`. Entrée Streamlit : `eurotyre_app.py`. URL existante : https://eurotyre-pricing-manager.streamlit.app/.

| Élément existant | Résultat de l’audit | Traitement |
| --- | --- | --- |
| Vue d’ensemble | Quatre écarts moyens Été, Hiver, Toutes saisons et Total | Conservés ; formule et nombre de références comparables précisés |
| Règles tarifaires | Remises BF par marque/saison et six tranches de diamètre ; lignes Marché informatives | Grille conservée, 0 % reste une remise explicite |
| Cellule vide | Appliquait auparavant la remise moyenne de la cellule à tous ses pneus, y compris à certains sans prix propre | Corrigée conformément au nouveau prompt : alignement exact sur le prix marché valide du pneu ; sans BF ou sans marché, pas de prix automatique |
| Import BF et marché | Mapping CSV/XLSX, validation atomique et historique | Conservé ; attributs profil, XL, runflat, homologation et véhicule ajoutés au BF |
| Catalogue | Contrôles et recommandations HT | Conservé ; reçoit le marché Radar de travail lorsque son alimentation est activée |
| Export | Marque, Saison, Code EAN, Prix HT, Remise BF (%) | Conservé ; export concurrentiel complémentaire ajouté |
| Versions | Brouillon, validation explicite, publication interne, instantanés | Conservées ; les collectes ne modifient aucune version ; un nouveau brouillon capture les prix/sources de travail |
| Persistance et droits | PostgreSQL, OIDC, rôles admin/pricing/viewer, révision optimiste | Conservés ; tables Radar séparées ; contrôles d’accès de collecte/validation côté Streamlit |
| Démo | 72 références fictives, sauvegarde de session | Conservée à l’ouverture ; pilote fictif de 200 références chargeable explicitement dans Radar |
| Données réelles | Aucun BF complet réel ou accès à une base de production identifié dans cette session | Aucun catalogue réel de 200 pneus ni historique réel annoncé comme disponible |

L’application n’a pas été reconstruite. Le logo, les règles enregistrées, les imports et les versions sont conservés. Le code est public : les données et contrats restent dans la base privée et les secrets, jamais dans le dépôt.

[Résultats des tests et vérifications restantes](RADAR_TESTS.md).

## Structure ajoutée

- `eurotyre/radar/catalog.py` : contrôle de clé EAN, sélection représentative et catalogue de test fictif.
- `matching.py` : EAN exact, marque/référence fabricant, rapprochement technique à valider ; empreintes d’identité.
- `prices.py` : conversion Decimal, TVA et comparabilité des prix.
- `connectors.py` : quatre adaptateurs indépendants pour flux JSON/CSV autorisés et import de fichiers.
- `pipeline.py` : orchestration, quarantaines et rapports d’exécution.
- `storage.py` : historique, validations et correspondances persistantes séparés.
- `market.py` : fraîcheur, médiane/moyenne/minimum/maximum, repli externe et indicateurs historiques.
- `ui.py` : comparaison, fiche historique, sélection, paramètres, imports, anomalies et exports.
- `cli.py` et `.github/workflows/market-radar.yml` : exécution indépendante de l’interface.

## Limites de la V1

Le test de persistance local utilise SQLite ; la production est prévue pour PostgreSQL externe. Sans connexion PostgreSQL/OIDC et sans flux autorisés réels, les tests de production ne peuvent pas être déclarés réussis. Le pilote fictif est signalé à l’écran et dans les rapports ; les simulations sont exclues des calculs de production.

La sélection automatique équilibre les groupes disponibles mais ne connaît pas les volumes du marché français. Une sélection pondérée par les ventes nécessiterait les volumes. Les imports/flux sont limités à 10 000 lignes et 5 Mo ; le pilote à 200 EAN. L’architecture conserve des tables indexées pour l’historique, mais l’extension à des milliers de pneus nécessitera pagination et collecte par lots.
