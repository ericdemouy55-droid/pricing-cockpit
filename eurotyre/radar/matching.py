"""Identité stricte ; les rapprochements techniques nécessitent une décision humaine."""
from hashlib import sha256
import json
from ..engine import norm, parse_ean, dimension, season
from .catalog import fingerprint, valid_ean, IDENTITY_FIELDS


def boolean(value):
    if value is True or norm(value) in ('true', '1', 'oui', 'yes'):
        return True
    if value is False or norm(value) in ('false', '0', 'non', 'no'):
        return False
    return None


def candidate_fingerprint(candidate):
    fields = {k: boolean(candidate.get(k)) if k in ('xl', 'runflat') else norm(candidate.get(k)) for k in IDENTITY_FIELDS}
    fields.update(ean=parse_ean(candidate.get('ean')))
    return sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def coherent(product, candidate):
    conflicts = []
    for field in IDENTITY_FIELDS:
        actual, expected = candidate.get(field), product.get(field)
        if field == 'homologation' and field in product and field in candidate:
            if norm(actual) != norm(expected):
                conflicts.append('Identité différente : homologation')
            continue
        # Une caractéristique omise n'invalide pas un EAN ou une référence fabricant exacts.
        if actual is None or actual == '' or expected is None or expected == '':
            continue
        if field in ('xl', 'runflat'):
            same = boolean(actual) is not None and boolean(actual) == boolean(expected)
        elif field == 'dimension':
            same = dimension(actual) == product.get('dimension')
        elif field == 'season':
            same = season(actual) == expected
        else:
            same = norm(actual) == norm(expected)
        if not same:
            conflicts.append(f'Identité différente : {field}')
    return conflicts


def match_candidate(products, candidate, mappings=()):
    ean = parse_ean(candidate.get('ean'))
    kind, quality = 'EAN', 100
    if ean:
        if not valid_ean(ean):
            return {'status': 'rejected', 'reasons': ['EAN concurrent invalide'], 'product': None}
        candidates = [p for p in products if p['ean'] == ean]
    elif candidate.get('ref') and candidate.get('brand'):
        kind, quality = 'Référence fabricant', 95
        candidates = [p for p in products if norm(p['ref']) == norm(candidate['ref']) and
                      norm(p['brand']) == norm(candidate['brand'])]
    else:
        kind, quality = 'Caractéristiques', 80
        required = ('brand', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat')
        if any(candidate.get(k) is None or candidate.get(k) == '' for k in required):
            return {'status': 'rejected', 'reasons': ['Identité technique incomplète'], 'product': None}
        candidates = [p for p in products if not coherent(p, candidate) and
                      all(p.get(k) is not None and p.get(k) != '' for k in required)]
    if len(candidates) != 1:
        return {'status': 'rejected', 'reasons': ['Correspondance ambiguë' if candidates else
                'Aucun produit pilote équivalent'], 'product': None}
    product = candidates[0]
    conflicts = coherent(product, candidate)
    if conflicts:
        return {'status': 'rejected', 'reasons': conflicts, 'product': product}
    pf, cf = fingerprint(product), candidate_fingerprint(candidate)
    valid_mapping = any(m['ean'] == product['ean'] and m['url'] == candidate.get('url') and
                        m['product_fingerprint'] == pf and m['candidate_fingerprint'] == cf
                        for m in mappings)
    # Ne pas transférer une validation sur une fiche dont les attributs ont changé.
    changed_mapping = any(m['url'] == candidate.get('url') and not
                          (m['ean'] == product['ean'] and m['product_fingerprint'] == pf and
                           m['candidate_fingerprint'] == cf) for m in mappings)
    pending = (kind == 'Caractéristiques' and not valid_mapping) or changed_mapping
    return {'status': 'pending' if pending else 'valid', 'product': product, 'quality': quality,
            'match': kind, 'product_fingerprint': pf, 'candidate_fingerprint': cf,
            'reasons': ['Fiche produit modifiée — nouvelle validation requise'] if changed_mapping else
                       ['Rapprochement technique à valider'] if pending else []}
