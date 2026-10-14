# Eurotyre Pricing Manager — Streamlit

## Parcours
1. Dans Imports, télécharger les modèles fictifs Excel/CSV. Importer le BF, puis le marché ; vérifier la feuille et associer les colonnes.
2. Un fichier remplace le référentiel courant du même type. Les lignes normalisées sont conservées dans chaque entrée de l’historique. Une erreur bloque l’ensemble de l’import.
3. Dimensions acceptées : 205/55R16, 205/55 R16, 225/45ZR18, ou colonnes largeur/série/diamètre. EAN : 13 chiffres ; références sans EAN : référence fabricant ou charge/vitesse requises. Les dates sont normalisées en AAAA-MM-JJ.
4. Dans Règles tarifaires, choisir Marque et Saison dans les menus en tête de grille. Saisir une remise BF en % dans les colonnes 13–14, 15, 16, 17, 18 et 19 pouces et +. Enregistrer les remises pour recalculer les prix.
5. Catalogue : contrôler le BF HT, le prix marché HT, le prix commerçant Eurotyre HT, leurs remises et les anomalies.
6. Export : consulter et télécharger en Excel/CSV les colonnes Marque, Saison, Code EAN, Prix HT et Remise BF (%). Le prix HT est le prix Eurotyre calculé. Les références sans prix calculé sont exclues, avec un compteur affiché. Les codes EAN sont conservés en texte, y compris les zéros initiaux.
7. Versions : créer un brouillon, valider sans anomalie, publier en interne. Un brouillon est un instantané ; après correction, créer une nouvelle version.
8. Les versions validées et publiées s’exportent en Excel/CSV. Aucun transfert aux ERP ou envoi aux franchisés n’est lancé.

## Modes et rôles
- Démo : jeu initial de 72 références fictives, session isolée ; modifications temporaires. Les modèles fournis ont 36 références totalement appariées, sans anomalies, pour tester l’export complet.
- Production : connexion OIDC (Google ou Microsoft), liste d’adresses autorisées par rôle, PostgreSQL externe. L’application refuse de démarrer si ces paramètres manquent.
- Administrateur : imports, paramètres, règles, versions et sauvegarde JSON.
- Responsable Pricing : règles, exports du tarif courant, validation et publication.
- Consultation : tableaux et exports validés ; aucune écriture autorisée.

## Export
- Administrateur et Responsable Pricing : tarif courant issu des règles enregistrées. Une saisie non enregistrée dans la grille BF ne modifie pas l’export.
- Consultation : sélectionner une version validée ou publiée ; aucune exportation d’un brouillon ou du tarif courant.
- Les fichiers contiennent exactement cinq colonnes, dans cet ordre : Marque, Saison, Code EAN, Prix HT, Remise BF (%).
- La remise BF est le taux appliqué : remise enregistrée si la cellule est renseignée, sinon remise équivalente au prix marché valide du pneu concerné. Les valeurs affichées sont arrondies à deux décimales. Les versions archivées conservent leurs prix et remises historiques.
- Les prix et remises absents ne sont pas inventés. Un code EAN manquant reste vide et est signalé. Les exports détaillés des versions validées restent disponibles dans Versions & diffusion.

## Règles tarifaires — remises BF
- Prix Eurotyre HT = BF HT × (1 − remise BF / 100), arrondi au centime. Remises de 0 à 99,99 % ; 0 % correspond au BF sans remise.
- Sous chaque ligne de saisie, la ligne « Marché (info) » indique la remise BF moyenne constatée pour cette marque, cette saison et cette tranche de diamètre : moyenne de (1 − prix marché HT / BF HT) × 100. Elle est en lecture seule et ne dépend pas des remises saisies.
- Sans prix marché comparable, la cellule affiche « — ». Les valeurs absentes ne sont pas remplacées par zéro. 19 pouces et + couvre les diamètres acceptés par le catalogue, jusqu’à 30 pouces.
- Les saisies sont conservées lors d’un changement de filtre, puis enregistrées ensemble. Elles restent temporaires en mode démo.
- Une remise BF renseignée est prioritaire, y compris 0 %. Une cellule vide s’aligne sur le prix marché valide propre à chaque EAN. Effacer une remise puis enregistrer rétablit cet alignement. Les anciennes variations restent archivées.
- La ligne Marché présente une moyenne informative. Son taux ne fournit jamais de prix à un autre pneu sans marché individuel. La remise implicite propre au pneu est calculée avant arrondi pour conserver l’alignement exact au centime. Sans BF ou prix marché valide, aucun prix automatique n’est créé.
- Les seuils contrôlent l’écart réel du prix Eurotyre au marché, et non le taux de remise BF. Les alertes de marché absent ou ambigu restent bloquantes pour valider une version, même si le prix Eurotyre peut être calculé à partir du BF.

## Vue d’ensemble — Outil prix Eurotyre
- Quatre indicateurs affichent l’écart moyen commerçant/marché toutes marques confondues : Été, Hiver, Toutes saisons, et Total. Chaque moyenne est calculée par référence comparable ; le Total porte sur l’ensemble des références des trois saisons.
- Les menus Marque et Saison filtrent le tableau des remises moyennes. Les quatre indicateurs portent sur l’ensemble du catalogue.
- Par marque et saison : écart moyen Eurotyre/marché en %, remise moyenne marché/BF et remise moyenne commerçant/BF.
- Remise par référence (%) = (1 − prix HT / BF HT) × 100.
- Par marque, toutes saisons confondues : écart moyen commerçant/marché.
- Écart par référence (%) = (prix commerçant Eurotyre HT / prix marché HT − 1) × 100. Positif : commerçant plus cher ; négatif : commerçant moins cher.
- Moyenne arithmétique des pourcentages par référence, sans pondération des volumes ni des prix. Les pourcentages sont arrondis à deux décimales après leur moyenne.
- Les trois indicateurs utilisent le même ensemble de références ayant BF, prix marché et prix commerçant calculé. Les valeurs absentes sont exclues et ne valent jamais zéro.
- Aucun calcul de marge ou de prix d’achat net. Les modèles BF ne demandent pas de prix d’achat net.

Le code source ne contient ni données réelles ni secrets. Le logo Eurotyre transmis par l’utilisateur est intégré dans la navigation.

