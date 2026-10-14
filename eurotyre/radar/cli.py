"""Ordonnanceur indépendant de Streamlit : python -m eurotyre.radar.cli."""
import argparse
import json
import os
from pathlib import Path
from ..storage import PostgresStore
from . import settings
from .catalog import select_pilot
from .connectors import configured_connectors
from .pipeline import collect
from .storage import PostgresRadarStore


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--migrate', action='store_true', help='Créer les tables si elles sont absentes, sans supprimer de données.')
    parser.add_argument('--workspace', default=os.getenv('RADAR_WORKSPACE', 'eurotyre'))
    args = parser.parse_args(argv)
    url = os.getenv('RADAR_DATABASE_URL')
    if not url:
        print('Collecte non démarrée : RADAR_DATABASE_URL non configuré.')
        return 2
    try:
        database = PostgresRadarStore(url)
        if args.migrate:
            import psycopg
            with psycopg.connect(url, connect_timeout=10) as con:
                con.execute('CREATE TABLE IF NOT EXISTS pricing_workspace (name TEXT PRIMARY KEY, payload JSONB NOT NULL, revision INTEGER NOT NULL DEFAULT 0)')
            database.migrate()
        state = PostgresStore(url).load(args.workspace)
        config = settings(state)
        products = select_pilot(state['products'], manual=config['selected_eans'])
        sources = json.loads(os.getenv('RADAR_SOURCES_JSON', '{}'))
        if not isinstance(sources, dict):
            raise ValueError('Configuration sources invalide')
        report = collect(products, configured_connectors(sources), database, config, args.workspace)
        # Les observations, prix, EAN, URLs, contrats et secrets restent dans la base privée.
        print(json.dumps({'run_id': report['id'], 'references': report['references'],
                          'connectors': report['connectors']}, ensure_ascii=False))
        return 1 if any(item['status'] == 'error' for item in report['connectors']) else 0
    except Exception:
        print('Collecte non confirmée : vérifier la base, le catalogue et les flux autorisés. Aucun secret n’est affiché.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
