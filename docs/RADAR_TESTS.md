# Validation du Market Price Radar

Commande : `python -m unittest discover -s tests -v`.

70 tests passent sur l’environnement Python 3.12 de développement. Les tests utilisent exclusivement des références, des fichiers et des réponses réseau fictifs. Ils ne constituent pas des essais de collecte réelle des enseignes.

| Périmètre | Vérification |
| --- | --- |
| Application existante | Navigation, quatre indicateurs, filtres BF, saisies conservées, remises explicites, export compact et accès production fermé sans configuration |
| Pilote | Import XLSX de 200 produits, clés EAN, unicité, sélection déterministe et couverture des groupes disponibles |
| Rapprochement | EAN exact, marque/référence fabricant, refus des conflits d’indices/saison/XL/runflat/profil/homologation, attente humaine pour identité technique |
| Prix | Decimal TTC/HT, conservation de l’original et du taux, rejet des prestations/frais/conditions non précisés, promotions et variations inhabituelles |
| Référence marché | Médiane/moyenne/minimum/maximum, enseignes distinctes, dates, fraîcheur, centres, repli externe unique et exclusion des simulations en production |
| Historique | Deux collectes identiques conservées, données absentes nulles, aucune date de relevé inventée, métriques 7/30/90 jours sans extrapolation |
| Validations | Observation d’origine conservée, décision séparée, correspondance réutilisée puis contrôlée, validation forcée d’un prix incompatible bloquée |
| Persistance | Réouverture du stockage SQLite de test, séparation des espaces et rapports conservés |
| Collecteurs | Refus avant requête sans autorisation ; flux JSON simulé ; absence de redirection/retry après 403 ; erreur d’un connecteur isolée |
| Confidentialité | Champs inconnus/jetons du flux non conservés ; aucun contrat, prix réel ou secret ajouté au dépôt |
| Exports | XLSX/CSV, EAN texte, prix numériques, valeurs absentes vides, cinq colonnes du tarif conservées |
| Parcours complet | 200 références × quatre enseignes × quatre dates = 3 200 observations simulées ; calculs et exports ; grille validée/publiée inchangée après une nouvelle collecte |

L’historique de simulation contient quatre dates et des jours sans données : le graphique ne relie pas les jours manquants. Les simulations restent dans le mode démonstration et ne servent jamais de prix de production.

## Vérifications restantes pour la production

- Appliquer et tester les migrations sur le PostgreSQL externe effectivement retenu ; vérifier TLS, sauvegardes/restauration, droits et accès OIDC réels.
- Importer les BF PLT réels et valider la composition du pilote de 200 EAN.
- Fournir pour chaque enseigne une autorisation ou un flux/fichier sous licence ; contrôler les prix, centres, identités et TVA sur quelques fiches réelles.
- Configurer et activer l’ordonnanceur, puis constater plusieurs exécutions indépendantes de Streamlit.
- Vérifier l’interface dans le navigateur après le redéploiement Streamlit. Les tests AppTest vérifient l’exécution de l’interface ; ils ne remplacent pas un contrôle visuel du service hébergé.

Aucun test contre une base PostgreSQL/OIDC réelle ni aucun connecteur marchand réel n’est annoncé comme réussi dans cette livraison.
