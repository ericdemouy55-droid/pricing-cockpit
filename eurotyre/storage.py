"""Persistance transactionnelle ; aucune donnée métier dans le dépôt GitHub."""
import json
import sqlite3
from copy import deepcopy
from .engine import demo

class ConflictError(ValueError):
    pass

class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as con:
            con.execute('CREATE TABLE IF NOT EXISTS pricing_workspace (name TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL)')

    def load(self, workspace='eurotyre'):
        with sqlite3.connect(self.path) as con:
            con.execute('INSERT OR IGNORE INTO pricing_workspace VALUES(?,?,0)', (workspace, json.dumps(demo())))
            payload, revision = con.execute('SELECT payload,revision FROM pricing_workspace WHERE name=?', (workspace,)).fetchone()
        state = json.loads(payload)
        state['revision'] = revision
        return state

    def save(self, state, expected_revision, workspace='eurotyre'):
        saved = deepcopy(state)
        saved['revision'] = expected_revision + 1
        with sqlite3.connect(self.path) as con:
            cursor = con.execute('UPDATE pricing_workspace SET payload=?,revision=? WHERE name=? AND revision=?', (json.dumps(saved), saved['revision'], workspace, expected_revision))
            if not cursor.rowcount:
                raise ConflictError('Une autre modification a été enregistrée. Recharge la page.')
        return saved

class PostgresStore:
    def __init__(self, url):
        self.url = url

    def load(self, workspace='eurotyre'):
        import psycopg
        from psycopg.types.json import Jsonb
        with psycopg.connect(self.url, connect_timeout=10) as con:
            con.execute('INSERT INTO pricing_workspace(name,payload,revision) VALUES(%s,%s,0) ON CONFLICT(name) DO NOTHING', (workspace, Jsonb(demo())))
            payload, revision = con.execute('SELECT payload,revision FROM pricing_workspace WHERE name=%s', (workspace,)).fetchone()
        payload['revision'] = revision
        return payload

    def save(self, state, expected_revision, workspace='eurotyre'):
        import psycopg
        from psycopg.types.json import Jsonb
        saved = deepcopy(state)
        saved['revision'] = expected_revision + 1
        with psycopg.connect(self.url, connect_timeout=10) as con:
            cursor = con.execute('UPDATE pricing_workspace SET payload=%s,revision=%s WHERE name=%s AND revision=%s', (Jsonb(saved), saved['revision'], workspace, expected_revision))
            if not cursor.rowcount:
                raise ConflictError('Une autre modification a été enregistrée. Recharge la page.')
        return saved
