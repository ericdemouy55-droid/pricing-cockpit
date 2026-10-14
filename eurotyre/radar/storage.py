"""Historique append-only, décisions humaines séparées et lectures indexées."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

SCHEMA = '''
CREATE TABLE IF NOT EXISTS radar_observation (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, run_id TEXT NOT NULL,
 ean TEXT NOT NULL, retailer TEXT NOT NULL, zone TEXT NOT NULL, center TEXT NOT NULL,
 observed_at TEXT, collected_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_observation_lookup
 ON radar_observation(workspace, ean, retailer, zone, center, observed_at);
CREATE INDEX IF NOT EXISTS radar_observation_recent
 ON radar_observation(workspace, observed_at);
CREATE TABLE IF NOT EXISTS radar_run (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_run_recent ON radar_run(workspace, started_at);
CREATE TABLE IF NOT EXISTS radar_review (
 id TEXT PRIMARY KEY, observation_id TEXT NOT NULL REFERENCES radar_observation(id),
 workspace TEXT NOT NULL, reviewed_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_review_lookup ON radar_review(workspace, observation_id, reviewed_at);
CREATE TABLE IF NOT EXISTS radar_mapping (
 workspace TEXT NOT NULL, retailer TEXT NOT NULL, url TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(workspace, retailer, url)
);
'''


class RadarStore:
    placeholder = '?'

    def sql(self, query):
        return query.replace('?', self.placeholder)

    def append(self, observations, report, workspace='eurotyre'):
        with self.connection() as con:
            for item in observations:
                con.execute(self.sql('INSERT INTO radar_observation VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING'),
                            (item['id'], workspace, report['id'], item.get('ean') or '', item['retailer'],
                             item.get('zone') or '', item.get('center') or '',
                             item.get('observed_at'), item.get('collected_at') or report['started_at'], json.dumps(item)))
            con.execute(self.sql('INSERT INTO radar_run VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING'),
                        (report['id'], workspace, report['started_at'], json.dumps(report)))

    def observations(self, workspace='eurotyre', ean=None, since=None):
        conditions, params = ['workspace=?'], [workspace]
        if ean:
            conditions.append('ean=?'); params.append(ean)
        if since:
            conditions.append('(observed_at>=? OR (observed_at IS NULL AND collected_at>=?))'); params.extend([since, since])
        with self.connection() as con:
            items = con.execute(self.sql('SELECT payload FROM radar_observation WHERE ' +
                                ' AND '.join(conditions) + ' ORDER BY COALESCE(observed_at,collected_at),id'), params).fetchall()
            reviews = con.execute(self.sql('SELECT observation_id,payload FROM radar_review WHERE workspace=? ORDER BY reviewed_at,id'),
                                  (workspace,)).fetchall()
        decisions = {oid: json.loads(payload) for oid, payload in reviews}
        result = []
        for (payload,) in items:
            item = json.loads(payload)
            decision = decisions.get(item['id'])
            if decision:
                item['review'] = decision
                if decision['accepted'] and item.get('status') == 'pending' and item.get('reviewable'):
                    item['status'] = 'valid'
                elif not decision['accepted']:
                    item['status'] = 'rejected'
            result.append(item)
        return result

    def runs(self, workspace='eurotyre', limit=20):
        with self.connection() as con:
            return [json.loads(row[0]) for row in con.execute(self.sql(
                'SELECT payload FROM radar_run WHERE workspace=? ORDER BY started_at DESC LIMIT ?'),
                (workspace, limit)).fetchall()]

    def mappings(self, retailer, workspace='eurotyre'):
        with self.connection() as con:
            return [json.loads(row[0]) for row in con.execute(self.sql(
                'SELECT payload FROM radar_mapping WHERE workspace=? AND retailer=?'), (workspace, retailer)).fetchall()]

    def review(self, observation_id, accepted, user, note, workspace='eurotyre'):
        if not str(note).strip():
            raise ValueError('Une justification de validation ou de rejet est requise.')
        with self.connection() as con:
            row = con.execute(self.sql('SELECT payload FROM radar_observation WHERE id=? AND workspace=?'),
                              (observation_id, workspace)).fetchone()
            if not row:
                raise ValueError('Observation introuvable.')
            item = json.loads(row[0])
            if accepted and not (item.get('status') == 'pending' and item.get('reviewable')):
                raise ValueError('Cette donnée ne peut pas être validée : corriger la source et refaire le relevé.')
            now = datetime.now(timezone.utc).isoformat()
            decision = {'accepted': bool(accepted), 'user': str(user), 'note': str(note)[:2000], 'date': now}
            con.execute(self.sql('INSERT INTO radar_review VALUES(?,?,?,?,?)'),
                        (str(uuid4()), observation_id, workspace, now, json.dumps(decision)))
            if accepted and item.get('url'):
                mapping = {k: item[k] for k in ('ean', 'url', 'product_fingerprint', 'candidate_fingerprint')}
                mapping['validated_by'], mapping['date'] = user, now
                con.execute(self.sql('INSERT INTO radar_mapping VALUES(?,?,?,?) ON CONFLICT(workspace,retailer,url) DO UPDATE SET payload=excluded.payload'),
                            (workspace, item['retailer'], item['url'], json.dumps(mapping)))
            elif not accepted and item.get('url'):
                con.execute(self.sql('DELETE FROM radar_mapping WHERE workspace=? AND retailer=? AND url=?'),
                            (workspace, item['retailer'], item['url']))


class SQLiteRadarStore(RadarStore):
    """Stockage de tests uniquement ; le disque de Streamlit Cloud n'est pas durable."""
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=10) as con:
            con.execute('PRAGMA foreign_keys=ON')
            yield con


class PostgresRadarStore(RadarStore):
    placeholder = '%s'

    def __init__(self, url):
        self.url = url

    @contextmanager
    def connection(self):
        import psycopg
        with psycopg.connect(self.url, connect_timeout=10) as con:
            yield con

    def migrate(self):
        with self.connection() as con:
            for query in SCHEMA.split(';'):
                if query.strip():
                    con.execute(query)
