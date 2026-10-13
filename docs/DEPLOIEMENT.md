# Déploiement GitHub + Streamlit

## Nouvelle version
Dépôt : `ericdemouy55-droid/pricing-cockpit`
Branche dédiée : `eurotyre-streamlit-v1`
Fichier principal : `eurotyre_app.py`
Python : 3.12.

L’ancien `app.py` est conservé. La nouvelle branche est distincte de `main`, afin de garder l’application précédente disponible.

## Démo Streamlit Community Cloud
1. Ouvrir https://share.streamlit.io et se connecter au compte lié à GitHub.
2. Cliquer sur Create app / New app et choisir un déploiement depuis GitHub.
3. Choisir le dépôt `ericdemouy55-droid/pricing-cockpit`, branche `eurotyre-streamlit-v1`, fichier `eurotyre_app.py`.
4. Choisir Python 3.12 dans Advanced settings. Aucun secret n’est nécessaire pour la démo fictive.
5. Déployer, puis ouvrir l’URL réellement attribuée. Ne pas considérer une adresse suggérée comme une URL active avant confirmation.

La démo est fonctionnelle et permet les imports fictifs/calculs/exports ; sa sauvegarde est limitée à la session Streamlit. Les fichiers locaux générés sur Community Cloud ne sont pas un stockage durable.

## Production avec données réelles
1. Choisir un PostgreSQL externe et exécuter `schema_postgres.sql` une fois. Utiliser une connexion TLS (`sslmode=require`).
2. Créer une application OIDC chez Google ou Microsoft avec le callback `https://VOTRE-APP.streamlit.app/oauth2callback`.
3. Dans les Secrets de Streamlit (jamais dans le dépôt), copier la structure `.streamlit/secrets.example.toml`, passer `app.mode` à `production`, renseigner database.url, les paramètres auth et les adresses autorisées par rôle.
4. Vérifier la connexion, le refus d’accès d’un compte absent, les rôles, une sauvegarde suivie d’un redémarrage et la reprise de l’espace.
5. Définir les sauvegardes et tester leur restauration chez le fournisseur PostgreSQL. Les secrets doivent rester hors GitHub.

L’authentification OIDC et l’adaptateur PostgreSQL sont implémentés mais ne peuvent pas être vérifiés contre une base et un fournisseur réels sans leur configuration. Aucun fournisseur payant n’a été provisionné automatiquement.

## Installation locale
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run eurotyre_app.py
```
Sous Windows, l’activation est `.venv\Scripts\activate`.
Tests : `python -m unittest discover -s tests -v`.

## Architecture
`eurotyre/engine.py` : Decimal, priorités, rapprochement indexé et anomalies.
`eurotyre/imports.py` : XLSX/CSV, mapping, dates/dimensions et erreurs.
`eurotyre/service.py` : contrôles de rôle, mutations, versions et traçabilité.
`eurotyre/storage.py` : PostgreSQL ; SQLite sert aux tests de persistance et de concurrence.
`eurotyre/exports.py` : exports et modèles, protection des cellules texte contre les formules.
`eurotyre_app.py` : interface Streamlit.

Les mises à jour utilisent une révision optimiste pour empêcher l’écrasement d’une modification concurrente. Les données partagent un espace centrale `eurotyre` en production, distinct de la session démo. Le journal est applicatif ; la V1 n’est pas un journal d’audit immuable.

Les imports sont limités à 5 Mo/10 000 lignes ; le payload cumulé est limité à 30 Mo. Pour les catalogues complets et de nombreuses versions, normaliser les tables PostgreSQL et paginer côté serveur.

## Passage de la démo GPT
Le moteur et les données fictives initiales ont été portés en Python. Cette application ne dépend pas de GPT ou de Base44. Les éventuelles modifications enregistrées dans l’ancienne base D1 ne sont pas importées automatiquement ; elles doivent être exportées et migrées séparément avant mise en production.
