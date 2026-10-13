# Eurotyre Pricing Manager — GitHub + Streamlit

V1 fonctionnelle de gestion des recommandations de prix publics HT des pneumatiques PLT. Nouvelle application : `eurotyre_app.py`. L’ancien `app.py` est conservé.

Démo Streamlit déployée le 13 octobre 2026 : **https://eurotyre-pricing-manager.streamlit.app/**.
Configuration active : branche `eurotyre-streamlit-v1`, fichier `eurotyre_app.py`, Python 3.12, mode démo sans secrets.

- Imports BF et marché réels XLSX/CSV avec assistant de mapping.
- Rapprochement EAN puis caractéristiques conservatrices ; aucune invention de marché.
- Règles prioritaires par marque, diamètre et saison, simulation et anomalies de marge.
- Versions brouillon/validée/publiée et exports complets Excel/CSV.
- Démo fictive sans configuration, isolée par session.
- Mode production : PostgreSQL externe, OIDC et profils administrateur/pricing/consultation.

Voir [Guide utilisateur](docs/GUIDE_UTILISATEUR.md) et [Déploiement](docs/DEPLOIEMENT.md).

```bash
pip install -r requirements.txt
streamlit run eurotyre_app.py
python -m unittest discover -s tests -v
```

La démo ne conserve pas les modifications après une fermeture complète de session. Pour une persistance durable, configurer PostgreSQL en mode production. Ne jamais committer `.streamlit/secrets.toml`, fichiers réels ou exports confidentiels.

