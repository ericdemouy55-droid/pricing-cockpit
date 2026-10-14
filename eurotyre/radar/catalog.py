"""Sélection déterministe à partir des BF, sans inventer de référence réelle."""
from collections import defaultdict, deque
from hashlib import sha256
import json
import re
from ..engine import decimal, norm, parse_ean, market_group, SEASONS

IDENTITY_FIELDS = ('brand', 'ref', 'profile', 'dimension', 'load', 'speed',
                   'season', 'xl', 'runflat', 'homologation')


def valid_ean(value):
    value = parse_ean(value)
    return bool(re.fullmatch(r'\d{13}', value) and
                (10 - sum(int(n) * (1 if i % 2 == 0 else 3)
                          for i, n in enumerate(value[:12])) % 10) % 10 == int(value[-1]))


def fingerprint(product):
    identity = {key: product.get(key) if key in ('xl', 'runflat') else norm(product.get(key)) for key in IDENTITY_FIELDS}
    return sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def eligible_catalog(products):
    counts = defaultdict(int)
    for product in products:
        counts[parse_ean(product.get('ean'))] += 1
    eligible, anomalies = [], []
    for product in products:
        ean = parse_ean(product.get('ean'))
        reasons = []
        if not valid_ean(ean):
            reasons.append('EAN absent ou clé de contrôle invalide')
        if counts[ean] > 1:
            reasons.append('Plusieurs lignes BF associées au même EAN')
        bf = decimal(product.get('bf'))
        if bf is None or bf <= 0:
            reasons.append('BF absent ou invalide')
        if not product.get('brand') or product.get('season') not in SEASONS or not product.get('dimension'):
            reasons.append('Identité produit incomplète')
        if reasons:
            anomalies.append({'ean': ean, 'brand': product.get('brand'), 'reasons': reasons})
        else:
            eligible.append(product)
    return eligible, anomalies


def select_pilot(products, size=200, manual=None):
    if not 1 <= size <= 200:
        raise ValueError('Le pilote accepte de 1 à 200 références.')
    eligible, _ = eligible_catalog(products)
    by_ean = {p['ean']: p for p in eligible}
    if manual is not None:
        if len(manual) > size or len(set(manual)) != len(manual):
            raise ValueError('Sélection limitée à 200 EAN uniques.')
        if any(ean not in by_ean for ean in manual):
            raise ValueError('La sélection contient un EAN absent ou invalide dans le BF courant.')
        return [by_ean[ean] for ean in manual]
    groups = defaultdict(list)
    for product in eligible:
        band = market_group(product['brand'], product['season'], product['diameter'])
        groups[(norm(product['brand']), product['season'], band[2:] if band else (),
                product.get('vehicle', 'Non renseigné'))].append(product)
    queues = [deque(sorted(values, key=lambda p: p['ean'])) for _, values in sorted(groups.items())]
    selected = []
    while queues and len(selected) < size:
        for queue in queues:
            if queue and len(selected) < size:
                selected.append(queue.popleft())
        queues = [queue for queue in queues if queue]
    return selected


def demo_catalog(size=200):
    """Uniquement pour le bouton explicite de simulation et les tests."""
    from ..engine import cash
    from datetime import date
    brands = ['Michelin', 'Continental', 'Goodyear', 'Bridgestone', 'Pirelli', 'Hankook', 'Falken']
    products = []
    for i in range(size):
        base = f'{290000000000 + i:012}'
        check = (10 - sum(int(n) * (1 if j % 2 == 0 else 3) for j, n in enumerate(base)) % 10) % 10
        diameter = 13 + (i // 21) % 9
        product = {
            'id': f'SIM-{i}', 'ean': base + str(check), 'ref': f'SIM-{i:04}',
            'manufacturer': brands[i % 7], 'brand': brands[i % 7],
            'profile': f'Gamme fictive {i % 4 + 1}',
            'dimension': f'{175 + (i % 7) * 10}/55 R{diameter}',
            'diameter': diameter, 'load': str(88 + i % 10), 'speed': 'V',
            'season': SEASONS[(i // 7) % 3], 'xl': bool(i % 2), 'runflat': False,
            'homologation': '', 'vehicle': ('Tourisme', 'SUV', 'VUL')[i % 3],
            'bf': cash(100 + (diameter - 13) * 22 + i % 11), 'validity': date.today().isoformat(),
        }
        products.append(product)
    return products
