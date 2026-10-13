"""Comparaisons HT, moyennes par référence sur un périmètre identique."""
from decimal import Decimal
from .engine import cash, decimal, norm, SEASONS

INDICATORS = ('market_discount', 'retailer_discount', 'market_gap')

def price_indicators(row):
    bf = decimal(row.get('bf'))
    market = decimal(row.get('market_price'))
    retailer = decimal(row.get('recommended'))
    def valid(value):
        return value is not None and value > 0
    return {
        'market_discount': (1 - market / bf) * 100 if valid(bf) and valid(market) else None,
        'retailer_discount': (1 - retailer / bf) * 100 if valid(bf) and valid(retailer) else None,
        'market_gap': (retailer / market - 1) * 100 if valid(market) and valid(retailer) else None,
    }

def overall_market_gap(rows):
    values = []
    for row in rows:
        indicators = price_indicators(row)
        if all(value is not None for value in indicators.values()):
            values.append(indicators['market_gap'])
    return cash(sum(values) / len(values)) if values else None

def summarize(rows, by_season=True):
    groups = {}
    for row in rows:
        brand = str(row.get('brand') or '').strip()
        season = row.get('season', '') if by_season else ''
        key = (norm(brand), season)
        group = groups.setdefault(key, {'brand': brand, 'season': season, 'references': 0,
                                      'compared': 0, 'totals': {k: Decimal(0) for k in INDICATORS}})
        group['references'] += 1
        indicators = price_indicators(row)
        # Les trois moyennes portent strictement sur les mêmes références.
        if all(value is not None for value in indicators.values()):
            group['compared'] += 1
            for name, value in indicators.items():
                group['totals'][name] += value
    result = []
    for group in groups.values():
        total = group.pop('totals')
        count = group['compared']
        result.append({**group, **{name: cash(total[name] / count) if count else None
                                  for name in INDICATORS}})
    seasons = {name: i for i, name in enumerate(SEASONS)}
    return sorted(result, key=lambda group: (norm(group['brand']), seasons.get(group['season'], 99)))
