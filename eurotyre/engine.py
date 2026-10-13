"""Calculs exacts en Decimal. Aucun prix de marché n'est extrapolé."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import re
import unicodedata
from uuid import uuid4

SEASONS = ('Été', 'Hiver', 'Toutes saisons')
DIAMETER_BANDS = (('13–14"', 13, 14), ('15"', 15, 15), ('16"', 16, 16),
                  ('17"', 17, 17), ('18"', 18, 18), ('19" et +', 19, 30))

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '').strip().lower()) if unicodedata.category(c) != 'Mn')

def cash(value):
    return str(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def decimal(value):
    text = str(value if value is not None else '').strip().replace('€', '').replace('\u00a0', '').replace(' ', '')
    if not text:
        return None
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    else:
        text = text.replace(',', '.')
    try:
        out = Decimal(text)
        return out if out.is_finite() else None
    except InvalidOperation:
        return None

def dimension(value):
    m = re.search(r'(\d{3})\s*[/_-]?\s*(\d{2})\s*Z?R?\s*(\d{2})(?:\s|[^0-9]|$)', str(value or '').upper())
    if not m:
        return ''
    w, h, d = map(int, m.groups())
    return f'{w}/{h} R{d}' if 125 <= w <= 395 and 20 <= h <= 95 and 13 <= d <= 30 else ''

def season(value):
    n = norm(value)
    for name, options in [('Été', ('ete', 'summer')), ('Hiver', ('hiver', 'winter')), ('Toutes saisons', ('4 saisons', 'toutes saisons', 'all season', 'all seasons', 'allseason', '4s'))]:
        if n in options:
            return name
    return ''

def parse_ean(value):
    txt = str(value or '').strip()
    if re.fullmatch(r'\d{13}\.0', txt):
        txt = txt[:-2]
    return txt

def parse_rule(rule):
    name = str(rule.get('id', '')).strip()
    brand = str(rule.get('brand', '') or '').strip()
    seas = str(rule.get('season', '') or '').strip()
    low, high = decimal(rule.get('min')), decimal(rule.get('max'))
    pricing_base = rule.get('base', 'market')
    if not name or len(name) > 80 or len(brand) > 80:
        raise ValueError('Nom de règle requis (80 caractères maximum).')
    if seas and seas not in SEASONS:
        raise ValueError('Saison de règle invalide.')
    if (low is None) != (high is None) or (low is not None and (low != int(low) or high != int(high) or not 13 <= low <= high <= 30)):
        raise ValueError('Diamètres : renseigne une plage entière entre 13 et 30 pouces.')
    if not brand and (low is not None or seas):
        raise ValueError('Une règle générale ne peut cibler un diamètre ou une saison.')
    parsed = {'id': name, 'brand': brand, 'min': int(low) if low else None,
              'max': int(high) if high else None, 'season': seas,
              'active': bool(rule.get('active', True))}
    if pricing_base == 'bf':
        discount = decimal(rule.get('discount'))
        if not brand or seas not in SEASONS or (low, high) not in [(a, b) for _, a, b in DIAMETER_BANDS]:
            raise ValueError('Une remise BF doit cibler une marque, une saison et une tranche de diamètre de la grille.')
        if discount is None or not 0 <= discount <= Decimal('99.99'):
            raise ValueError('Remise BF entre 0 % et 99,99 % requise.')
        return {**parsed, 'base': 'bf', 'discount': cash(discount)}
    if pricing_base != 'market':
        raise ValueError('Base de calcul inconnue.')
    variation = decimal(rule.get('variation'))
    if variation is None or not -90 <= variation <= 100:
        raise ValueError('Variation entre −90 % et +100 % requise.')
    return {**parsed, 'variation': str(variation)}

def priority(r):
    if r.get('base') == 'bf':
        return 6
    return (5 if r['season'] else 4) if r['brand'] and r['min'] is not None else (3 if r['season'] else 2) if r['brand'] else 1

def rule_conflicts(rules):
    rules = [r for r in rules if r['active']]
    out = []
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            if priority(a) == priority(b) and norm(a['brand']) == norm(b['brand']) and (not a['season'] or not b['season'] or a['season'] == b['season']) and max(a['min'] or 0, b['min'] or 0) <= min(a['max'] or 99, b['max'] or 99):
                out.append(f"{a['id']} / {b['id']}")
    return out

def market_group(brand, season, diameter):
    for _, low, high in DIAMETER_BANDS:
        if low <= diameter <= high:
            return norm(brand), season, low, high
    return None

def market_discount_reference(rows):
    """Remise marché moyenne par cellule, arrondie comme la ligne Marché de la grille."""
    groups = {}
    for row in rows:
        bf, market = decimal(row.get('bf')), decimal(row.get('market_price'))
        key = market_group(row['brand'], row['season'], row['diameter'])
        if key is not None and bf is not None and bf > 0 and market is not None and market > 0:
            groups.setdefault(key, []).append((1 - market / bf) * 100)
    return {key: cash(sum(values) / len(values)) for key, values in groups.items()}

def match_products(state):
    by_ean, by_ref, by_tech = {}, {}, {}
    def base(p):
        return (norm(p['brand']), p['dimension'], p['season'])
    for i, m in enumerate(state['market']):
        if m['ean']:
            by_ean.setdefault(m['ean'], []).append(i)
        if m['ref']:
            by_ref.setdefault(base(m) + (m['ref'],), []).append(i)
        if m['load'] and m['speed']:
            by_tech.setdefault(base(m) + (m['load'], m['speed']), []).append(i)
    result = []
    for p in state['products']:
        indices = by_ean.get(p['ean'], []) if p['ean'] else []
        match = 'EAN'
        if not indices:
            indices = sorted(set((by_ref.get(base(p) + (p['ref'],), []) if p['ref'] else []) + (by_tech.get(base(p) + (p['load'], p['speed']), []) if p['load'] and p['speed'] else [])))
            match = 'Caractéristiques'
        alerts = []
        if len(indices) > 1:
            alerts.append('Correspondance ambiguë')
        elif not indices:
            alerts.append('Prix marché absent')
        market = decimal(state['market'][indices[0]]['price']) if len(indices) == 1 else None
        product = {k: v for k, v in p.items() if k not in ('net', 'margin_eur', 'margin', 'markup')}
        result.append({**product, 'market_price': cash(market) if market is not None else None,
                       'match': match if market is not None else 'Non rapproché', 'alerts': alerts})
    return result

def calculate(state, rules=None):
    rules = state['rules'] if rules is None else rules
    # Les anciennes variations restent archivées mais ne remplacent jamais une
    # cellule BF vide : son taux provient désormais de la ligne Marché.
    rules = [r for r in rules if r.get('base') == 'bf' and r['active']]
    matched = match_products(state)
    reference = market_discount_reference(matched)
    result = []
    for p in matched:
        market = decimal(p['market_price'])
        alerts = list(p['alerts'])
        applicable = [r for r in rules if norm(r['brand']) == norm(p['brand']) and
                      r['min'] <= p['diameter'] <= r['max'] and r['season'] == p['season']]
        rule = applicable[0] if applicable else None
        if len(applicable) > 1:
            alerts.append('Conflit de règles')
        discount = decimal(rule['discount']) if rule else decimal(reference.get(
            market_group(p['brand'], p['season'], p['diameter'])))
        if discount is None:
            alerts.append('Remise marché indisponible')
        pv, variation = None, None
        bf = decimal(p.get('bf'))
        if bf is None or bf <= 0:
            alerts.append('BF absent ou invalide')
        elif discount is not None and 'Conflit de règles' not in alerts:
            pv = Decimal(cash(bf * (1 - discount / 100)))
        if pv is not None and pv <= 0:
            alerts.append('PV nul après arrondi au centime')
            pv = None
        if pv is not None and market is not None and market > 0:
            variation = (pv / market - 1) * 100
        if variation is not None and abs(variation) > Decimal(str(state['settings']['max_deviation'])):
            alerts.append('Écart marché excessif')
        result.append({**p, 'variation': cash(variation) if variation is not None else None,
            'recommended': cash(pv) if pv is not None else None,
            'delta': cash(pv - market) if pv is not None and market is not None else None,
            'rule': rule['id'] if rule else 'Remise marché (automatique)' if discount is not None else '',
            'applied_discount': cash(discount) if discount is not None else None,
            'discount_source': 'bf' if rule else 'market' if discount is not None else None,
            'alerts': alerts})
    return result

def demo():
    brands = ['Michelin', 'Continental', 'Bridgestone', 'Goodyear', 'Pirelli', 'Hankook']
    products, market = [], []
    for i in range(72):
        d, b, s = 15 + i % 7, brands[i % 6], SEASONS[(i // 6) % 3]
        price = Decimal(55 + (d - 15) * 18 + (i % 6) * 6)
        p = {'id': str(uuid4()), 'ean': f'2000000{i:06}', 'ref': f'DEMO-{i + 1}', 'manufacturer': b, 'brand': b, 'dimension': f'{195 + (i % 6) * 10}/{40 if d > 18 else 55} R{d}', 'diameter': d, 'load': '94', 'speed': 'V', 'season': s, 'bf': cash(price * Decimal('1.6')), 'validity': '2026-10-01'}
        products.append(p)
        if i % 13:
            market.append({k: p[k] for k in ('ean', 'ref', 'brand', 'dimension', 'load', 'speed', 'season')} | {'price': cash(price), 'date': '2026-10-13', 'source': 'Données fictives'})
    rules = [parse_rule({'id': 'Générale', 'brand': '', 'min': None, 'max': None, 'season': '', 'variation': 0}), parse_rule({'id': 'Michelin', 'brand': 'Michelin', 'min': None, 'max': None, 'season': '', 'variation': 3}), parse_rule({'id': 'Continental 17+ 4S', 'brand': 'Continental', 'min': 17, 'max': 30, 'season': 'Toutes saisons', 'variation': -2})]
    return {'products': products, 'market': market, 'rules': rules, 'baseline': deepcopy(rules), 'imports': [], 'versions': [], 'audit': [], 'settings': {'max_deviation': 15}, 'revision': 0}

