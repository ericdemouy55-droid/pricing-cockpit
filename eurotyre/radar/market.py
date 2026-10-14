"""Référence de travail par EAN, datée, sans pondérer une enseigne plusieurs fois."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from statistics import median
from ..engine import cash, decimal
from . import RETAILERS
from .catalog import fingerprint
from .matching import match_candidate
from .prices import timestamp


def summary(products, observations, config, external=(), now=None, allow_simulated=False):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=config['freshness_days'])
    by_ean = {p['ean']: p for p in products}
    external_by_ean = {}
    for item in external:
        matched = match_candidate(products, item)
        if matched['status'] == 'valid' and matched['product'] is not None:
            external_by_ean.setdefault(matched['product']['ean'], []).append(item)
    usable, conflicts = {}, set()
    for item in observations:
        ean, retailer = item.get('ean'), item.get('retailer')
        if ean not in by_ean or retailer not in RETAILERS or item.get('status') != 'valid':
            continue
        if item.get('simulated') and not allow_simulated:
            continue
        if item.get('zone') != config['zone'] or not config['centers'].get(retailer) or item.get('center') != config['centers'][retailer]:
            continue
        if item.get('product_fingerprint') != fingerprint(by_ean[ean]):
            continue
        try:
            date = timestamp(item['observed_at'])
        except (ValueError, TypeError):
            continue
        value = decimal(item.get('price_ht'))
        if not cutoff <= date <= now or value is None or value <= 0:
            continue
        if item.get('promotion') and not config['include_promotions']:
            continue
        key = ean, retailer
        previous = usable.get(key)
        if previous and date == timestamp(previous['observed_at']) and value != decimal(previous['price_ht']):
            conflicts.add((key, date))
        if previous is None or date >= timestamp(previous['observed_at']):
            usable[key] = item
    result = {}
    for ean, product in by_ean.items():
        retailers = {name: usable.get((ean, name)) for name in RETAILERS}
        for name, item in retailers.items():
            if item and ((ean, name), timestamp(item['observed_at'])) in conflicts:
                retailers[name] = None
        values = [decimal(o['price_ht']) for o in retailers.values() if o]
        reference, source, last = None, 'Non disponible', None
        stats = {'min': None, 'max': None, 'mean': None, 'median': None}
        if values:
            stats = {'min': cash(min(values)), 'max': cash(max(values)),
                     'mean': cash(sum(values) / len(values)), 'median': cash(median(values))}
            reference = stats[config['method']]
            source = f'Radar · {config["method"]} · {len(values)} enseigne(s)'
            last = max(o['observed_at'] for o in retailers.values() if o)
        else:
            candidates = [o for o in external_by_ean.get(ean, []) if
                          decimal(o.get('price')) is not None and decimal(o['price']) > 0]
            if len(candidates) == 1:
                item = candidates[0]
                try:
                    # Les anciens imports stockent une date sans heure, conservée comme telle.
                    date = timestamp(item['date']) if 'T' in str(item.get('date')) else datetime.fromisoformat(item['date']).replace(tzinfo=timezone.utc)
                    if cutoff <= date <= now:
                        reference, source, last = cash(item['price']), 'Référentiel externe · ' + str(item.get('source') or 'fichier'), item['date']
                except (ValueError, TypeError, KeyError):
                    pass
        result[ean] = {'ean': ean, 'retailers': retailers, 'reference': reference,
                       'count': len(values), 'source': source, 'last': last, **stats,
                       'quality': 'Prix concurrents validés' if values else 'Repli externe' if reference else 'Non disponible'}
    return result


def history_metrics(observations, now=None):
    now = now or datetime.now(timezone.utc)
    valid = []
    for item in observations:
        if item.get('status') != 'valid' or decimal(item.get('price_ht')) is None:
            continue
        try:
            date = timestamp(item['observed_at'])
            if date <= now:
                valid.append((date, decimal(item['price_ht'])))
        except (ValueError, TypeError):
            pass
    valid.sort(key=lambda pair: pair[0])
    if not valid:
        return {key: None for key in ('current', 'previous', 'last_variation', 'variation_7', 'variation_30', 'variation_90', 'min', 'max', 'changes')}
    last, current = valid[-1]
    previous = valid[-2][1] if len(valid) > 1 else None
    variation = lambda price: cash((current / price - 1) * 100) if price is not None and price > 0 else None
    result = {'current': cash(current), 'previous': cash(previous) if previous is not None else None,
              'last_variation': variation(previous), 'min': cash(min(p for _, p in valid)),
              'max': cash(max(p for _, p in valid)),
              'changes': sum(a[1] != b[1] for a, b in zip(valid, valid[1:]))}
    for days in (7, 30, 90):
        target = last - timedelta(days=days)
        baseline = next((p for d, p in reversed(valid) if target - timedelta(days=7) <= d <= target), None)
        result[f'variation_{days}'] = variation(baseline)
    return result


def comparison_frame(products, summaries, pricing_rows):
    import pandas as pd
    from ..exports import safe_text
    prices = {r['ean']: r.get('recommended') for r in pricing_rows}
    records = []
    for p in products:
        s = summaries.get(p['ean'], {})
        market, price = decimal(s.get('reference')), decimal(prices.get(p['ean']))
        record = {'EAN': safe_text(p['ean']), 'Marque': safe_text(p['brand']), 'Dimension': p['dimension'], 'Saison': p['season']}
        for name in RETAILERS:
            item = s.get('retailers', {}).get(name)
            record[name + ' HT'] = float(item['price_ht']) if item else None
        record.update({'Prix marché HT': float(market) if market else None,
                       'Prix Eurotyre HT': float(price) if price else None,
                       'Écart Eurotyre / marché %': float(cash((price / market - 1) * 100)) if market and price else None,
                       'Enseignes comparées': s.get('count', 0), 'Dernier relevé': s.get('last'),
                       'Source': safe_text(s.get('source')), 'Statut de qualité': s.get('quality', 'Non disponible')})
        records.append(record)
    return pd.DataFrame(records, columns=['EAN', 'Marque', 'Dimension', 'Saison'] +
        [n + ' HT' for n in RETAILERS] + ['Prix marché HT', 'Prix Eurotyre HT',
        'Écart Eurotyre / marché %', 'Enseignes comparées', 'Dernier relevé', 'Source', 'Statut de qualité'])
