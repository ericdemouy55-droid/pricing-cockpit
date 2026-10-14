"""Collecte isolée par enseigne ; aucune mutation de version/prix publiés."""
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4
from ..engine import decimal
from .catalog import eligible_catalog
from .matching import match_candidate
from .prices import normalize, timestamp


def collect(products, connectors, store, config, workspace='eurotyre', now=None):
    now = now or datetime.now(timezone.utc)
    eligible, issues = eligible_catalog(products)
    if issues:
        raise ValueError('Le catalogue pilote contient des EAN, doublons ou BF invalides.')
    if len(products) > 200:
        raise ValueError('200 références maximum pour ce pilote.')
    report = {'id': str(uuid4()), 'started_at': now.isoformat(), 'finished_at': None,
              'references': len(eligible), 'zone': config['zone'], 'connectors': [], 'simulated': False}
    observations = []
    history = store.observations(workspace)
    previous_prices = {(o.get('ean'), o['retailer'], o.get('zone'), o.get('center')): o
                       for o in history if o.get('status') == 'valid'}
    for connector in connectors:
        detail = {'retailer': connector.name, 'status': 'disabled', 'observations': 0,
                  'valid': 0, 'pending': 0, 'rejected': 0, 'missing': 0}
        batch = []
        try:
            if not eligible:
                detail['message'] = 'Aucune référence sélectionnée'
                report['connectors'].append(detail)
                continue
            candidates = connector.fetch(eligible, config)
            mappings = store.mappings(connector.name, workspace)
            for candidate in candidates:
                # Limiter les champs conservés : aucune clé/credential du flux n'est historisée.
                fields = ('ean', 'ref', 'brand', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat',
                          'homologation', 'url', 'price', 'price_type', 'currency', 'tax_rate', 'nature',
                          'mounting_included', 'delivery_included', 'member_only', 'conditional_price', 'promotion',
                          'promotion_conditions', 'usual_price', 'observed_at', 'zone', 'center', 'availability',
                          'mounting_fee', 'delivery_fee', 'simulated', 'authorization')
                candidate = {key: candidate[key] for key in fields if key in candidate}
                match = match_candidate(eligible, candidate, mappings)
                product = match.pop('product')
                ean = product['ean'] if product else str(candidate.get('ean') or '')
                previous = previous_prices.get((ean, connector.name, candidate.get('zone'), candidate.get('center')))
                price = normalize(candidate, now, previous, config['freshness_days'], config['max_price_change'])
                reasons = match['reasons'] + price['reasons']
                blocking_scope = []
                if not candidate.get('url') or not str(candidate['url']).startswith('https://'):
                    blocking_scope.append('URL source HTTPS absente')
                if not candidate.get('zone') or not candidate.get('center'):
                    blocking_scope.append('Centre ou zone non précisé')
                if candidate.get('zone') != config['zone']:
                    blocking_scope.append('Zone différente du pilote')
                configured_center = config.get('centers', {}).get(connector.name)
                if configured_center and candidate.get('center') != configured_center:
                    blocking_scope.append('Centre différent du centre sélectionné')
                reasons += blocking_scope
                bf = decimal(product.get('bf')) if product else None
                ht = decimal(price.get('price_ht'))
                if bf and ht and not bf * decimal('.05') <= ht <= bf * 3:
                    reasons.append('Prix anormal par rapport au BF')
                status = 'rejected' if 'rejected' in (match['status'], price['status']) or blocking_scope else 'pending' if reasons else 'valid'
                item = {
                    **candidate, **match, **price, 'status': status, 'reasons': reasons,
                    'id': str(uuid4()), 'run_id': report['id'], 'ean': ean,
                    'retailer': connector.name, 'collected_at': now.isoformat(),
                    'source_ean': candidate.get('ean'), 'target_product': dict(product) if product else None,
                    'reviewable': bool(product) and status == 'pending' and price['reviewable'] and not blocking_scope,
                }
                batch.append(item)
            counts = Counter((o['ean'], o.get('zone'), o.get('center')) for o in batch if o['ean'])
            for item in batch:
                if counts[(item['ean'], item.get('zone'), item.get('center'))] > 1:
                    item['status'], item['reviewable'] = 'rejected', False
                    item['reasons'].append('Plusieurs offres associées au même EAN/centre dans ce flux')
            present = {item['ean'] for item in batch}
            for product in eligible:
                if product['ean'] not in present:
                    batch.append({'id': str(uuid4()), 'run_id': report['id'], 'ean': product['ean'],
                        'retailer': connector.name, 'zone': config['zone'],
                        'center': config.get('centers', {}).get(connector.name, ''),
                        'observed_at': now.isoformat(), 'collected_at': now.isoformat(),
                        'status': 'missing', 'price_ht': None, 'reviewable': False,
                        'reasons': ['Prix non disponible dans ce relevé'],
                        'simulated': bool(getattr(connector, 'simulated', False))})
            detail.update(status='completed', observations=len(batch))
            for item in batch:
                detail[item['status']] += 1
            report['simulated'] |= any(item.get('simulated') for item in batch)
        except PermissionError as e:
            batch = []
            detail.update(status='disabled', message=str(e))
        except Exception:
            batch = []
            detail.update(status='error', message='Erreur de lecture ou de traitement du connecteur ; les autres enseignes continuent.')
        observations.extend(batch)
        report['connectors'].append(detail)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    store.append(observations, report, workspace)
    return report
