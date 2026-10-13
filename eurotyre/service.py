from copy import deepcopy
from datetime import datetime, timezone
import json
from .engine import calculate, parse_rule, rule_conflicts, decimal
from .imports import import_rows

PERMISSIONS = {'admin': {'import', 'rules', 'settings', 'baseline', 'version', 'validate', 'publish'}, 'pricing': {'rules', 'settings', 'baseline', 'version', 'validate', 'publish'}, 'viewer': set()}

def mutate(state, action, role, user='Démo', **params):
    if action not in PERMISSIONS.get(role, set()):
        raise PermissionError('Ton profil ne permet pas cette opération.')
    s = deepcopy(state)
    now = datetime.now(timezone.utc).isoformat()
    if action == 'import':
        rows, errors = import_rows(params['rows'], params['mapping'], params['kind'])
        if errors:
            raise ValueError('Import entièrement bloqué :\n' + '\n'.join(errors[:20]))
        field = 'products' if params['kind'] == 'bf' else 'market'
        s[field] = rows
        s['imports'].insert(0, {'date': now, 'name': str(params['name'])[:200], 'kind': params['kind'], 'count': len(rows), 'rows': deepcopy(rows)})
        detail = f"Import {params['kind']} : {len(rows)} lignes"
    elif action == 'rules':
        if len(params['rules']) > 500:
            raise ValueError('500 règles maximum.')
        rules = [parse_rule(r) for r in params['rules']]
        if len({r['id'] for r in rules}) != len(rules):
            raise ValueError('Les noms de règles doivent être uniques.')
        s['rules'] = rules
        detail = 'Modification des règles'
    elif action == 'settings':
        b = decimal(params['max_deviation'])
        if b is None or not 0 <= b <= 100:
            raise ValueError('Seuils invalides.')
        s['settings'] = {'max_deviation': float(b)}
        detail = 'Modification des seuils'
    elif action == 'baseline':
        s['baseline'] = deepcopy(s['rules'])
        detail = 'Scénario de référence enregistré'
    elif action == 'version':
        s['versions'].insert(0, {'id': f"V{len(s['versions']) + 1}", 'date': now, 'status': 'Brouillon', 'rows': calculate(s), 'rules': deepcopy(s['rules']), 'settings': deepcopy(s['settings'])})
        detail = 'Création version brouillon'
    elif action in ('validate', 'publish'):
        version = next((v for v in s['versions'] if v['id'] == params['id']), None)
        if not version:
            raise ValueError('Version introuvable.')
        if action == 'validate':
            if version['status'] != 'Brouillon':
                raise ValueError('Brouillon requis.')
            if not version['rows'] or any(r['alerts'] for r in version['rows']) or rule_conflicts(version['rules']):
                raise ValueError('Validation bloquée : résous toutes les anomalies, puis crée un nouveau brouillon.')
            version['status'] = 'Validée'
        else:
            if version['status'] != 'Validée':
                raise ValueError('Version validée requise.')
            version['status'] = 'Publiée'
        detail = f"{'Validation' if action == 'validate' else 'Publication interne'} {version['id']}"
    else:
        raise ValueError('Opération inconnue.')
    s['audit'].insert(0, {'date': now, 'user': user, 'action': detail})
    if len(json.dumps(s).encode()) > 30 * 1024 * 1024:
        raise ValueError('Espace de démonstration limité à 30 Mo. Archive les versions en dehors de cet espace pour agrandir le catalogue.')
    return s

