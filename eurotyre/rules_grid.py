"""Grille de remises BF et références marché, sans modifier les règles existantes."""
from hashlib import sha256
from .engine import DIAMETER_BANDS, SEASONS, norm, parse_rule, rule_conflicts, market_discount_reference


def cell_key(brand, season, low, high):
    identity = f'{norm(brand)}|{season}|{low}|{high}'
    return sha256(identity.encode()).hexdigest()[:24]


def grid_brands(state):
    brands = {}
    for item in state['products'] + state['rules']:
        brand = str(item.get('brand') or '').strip()
        if brand:
            brands.setdefault(norm(brand), brand)
    return sorted(brands.values(), key=norm)


def saved_discounts(rules):
    return {cell_key(r['brand'], r['season'], r['min'], r['max']): r['discount']
            for r in rules if r.get('base') == 'bf' and r['active']}


def market_discounts(rows):
    """Moyenne des remises marché/BF par référence rapprochée, même sans PV calculé."""
    return {cell_key(*key): value for key, value in market_discount_reference(rows).items()}


def apply_discounts(state, changes):
    """Fusion atomique des cellules modifiées ; une cellule vide retire sa remise BF."""
    if not changes:
        raise ValueError('Aucune remise modifiée.')
    known_brands = {norm(brand): brand for brand in grid_brands(state)}
    cells = {}
    for change in changes:
        brand = known_brands.get(norm(change.get('brand')))
        season = change.get('season')
        low, high = change.get('min'), change.get('max')
        if not brand or season not in SEASONS or (low, high) not in [(a, b) for _, a, b in DIAMETER_BANDS]:
            raise ValueError('Cellule de la grille invalide.')
        key = cell_key(brand, season, low, high)
        if key in cells:
            raise ValueError('Une cellule ne peut être modifiée qu’une fois.')
        value = change.get('discount')
        empty = value is None or (isinstance(value, str) and not value.strip())
        cells[key] = None if empty else parse_rule({
            'id': f'BF {key}', 'brand': brand, 'season': season, 'min': low, 'max': high,
            'base': 'bf', 'discount': value, 'active': True})
    rules = [r for r in state['rules'] if not (
        r.get('base') == 'bf' and cell_key(r['brand'], r['season'], r['min'], r['max']) in cells)]
    rules += [r for r in cells.values() if r is not None]
    if len(rules) > 500:
        raise ValueError('500 règles maximum.')
    if len({r['id'] for r in rules}) != len(rules):
        raise ValueError('Les noms de règles doivent être uniques.')
    # Les anciennes variations restent archivées. Les nouvelles cellules BF ne
    # peuvent introduire d’ambiguïté dans la grille.
    if rule_conflicts([r for r in rules if r.get('base') == 'bf']):
        raise ValueError('Conflit entre les remises BF.')
    return rules
