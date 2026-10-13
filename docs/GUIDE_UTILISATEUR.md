# Eurotyre Pricing Manager — Streamlit

## Parcours
1. Dans Imports, télécharger les modèles fictifs Excel/CSV. Importer le BF, puis le marché ; vérifier la feuille et associer les colonnes.
2. Un fichier remplace le référentiel courant du même type. Les lignes normalisées sont conservées dans chaque entrée de l’historique. Une erreur bloque l’ensemble de l’import.
3. Dimensions acceptées : 205/55R16, 205/55 R16, 225/45ZR18, ou colonnes largeur/série/diamètre. EAN : 13 chiffres ; références sans EAN : référence fabricant ou charge/vitesse requises. Les dates sont normalisées en AAAA-MM-JJ.
4. Dans Règles, créer une marque/plage de diamètres/saison. Min = max pour un diamètre unique. Général : laisser les critères vides. Les pourcentages ne s’additionnent pas. Enregistrer pour recalculer.
5. Catalogue : contrôler les prix HT et les anomalies. Marge brute = PV − PA ; taux de marque = marge / PV ; taux de marge = marge / PA. Le BF ne sert jamais de PA net.
6. Simulation : figer un scénario de référence puis modifier les règles actuelles. La comparaison porte sur les données actuellement importées.
7. Versions : créer un brouillon, valider sans anomalie, publier en interne. Un brouillon est un instantané ; après correction, créer une nouvelle version.
8. Les versions validées et publiées s’exportent en Excel/CSV. Aucun transfert aux ERP ou envoi aux franchisés n’est lancé.

## Modes et rôles
- Démo : jeu initial de 72 références fictives, session isolée ; modifications temporaires. Les modèles fournis ont 36 références totalement appariées, sans anomalies, pour tester l’export complet.
- Production : connexion OIDC (Google ou Microsoft), liste d’adresses autorisées par rôle, PostgreSQL externe. L’application refuse de démarrer si ces paramètres manquent.
- Administrateur : imports, paramètres, règles, versions et sauvegarde JSON.
- Responsable Pricing : règles, simulations, validation et publication.
- Consultation : tableaux et exports validés ; aucune écriture autorisée.

Le code source ne contient ni données réelles ni secrets. L’en-tête Eurotyre est typographique, en attendant le logo officiel.
