"""Normalisation Decimal ; aucun prix de prestation n'alimente le marché."""
from datetime import datetime, timezone, timedelta
from ..engine import decimal, cash, norm
from .matching import boolean


def timestamp(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Date/heure avec fuseau obligatoire (ISO 8601).')
    return dt.astimezone(timezone.utc)


def normalize(candidate, now=None, previous=None, freshness_days=7, max_change=30):
    now = now or datetime.now(timezone.utc)
    reasons, blocking = [], []
    price = decimal(candidate.get('price'))
    if price is None or not 0 < price <= 100000:
        blocking.append('Prix absent, nul, négatif ou hors plage')
    tax_type = str(candidate.get('price_type', '')).upper()
    if tax_type not in ('HT', 'TTC'):
        blocking.append('Type HT/TTC absent ou inconnu')
    currency = str(candidate.get('currency', '')).upper()
    if currency != 'EUR':
        blocking.append('Devise non comparable')
    rate = decimal(candidate.get('tax_rate'))
    if tax_type == 'TTC' and (rate is None or not 0 <= rate <= 100):
        blocking.append('Taux de TVA absent ou invalide')
    if candidate.get('nature') != 'pneu_seul':
        blocking.append('Nature du prix non comparable : pneu seul requis')
    for key, label in (('mounting_included', 'montage'), ('delivery_included', 'livraison'),
                       ('member_only', 'adhérent'), ('conditional_price', 'condition particulière')):
        if boolean(candidate.get(key)) is not False:
            blocking.append(f'Prix avec {label} ou composition non précisée')
    promotion = boolean(candidate.get('promotion'))
    if promotion is None:
        blocking.append('Promotion non identifiée')
    if promotion and not str(candidate.get('promotion_conditions', '')).strip():
        blocking.append('Conditions de promotion absentes')
    try:
        observed = timestamp(candidate.get('observed_at'))
        if observed > now + timedelta(minutes=5):
            blocking.append('Date de relevé dans le futur')
        if observed < now - timedelta(days=freshness_days):
            reasons.append('Relevé trop ancien')
    except (ValueError, TypeError):
        observed = None
        blocking.append('Date/heure avec fuseau absente ou invalide')
    ht = None
    if price is not None and price > 0 and tax_type in ('HT', 'TTC') and (tax_type == 'HT' or rate is not None and 0 <= rate <= 100):
        ht = decimal(cash(price / (1 + rate / 100) if tax_type == 'TTC' else price))
        if ht <= 0:
            blocking.append('Prix HT nul après arrondi')
    usual = decimal(candidate.get('usual_price'))
    if promotion is False and usual is not None and price is not None and price < usual:
        blocking.append('Réduction du prix habituel sans promotion identifiée')
    if previous and ht is not None:
        prev = decimal(previous.get('price_ht'))
        if prev and abs((ht / prev - 1) * 100) > max_change:
            reasons.append('Variation de prix inhabituelle')
    return {
        'price_original': cash(price) if price is not None else None,
        'price_type': tax_type, 'tax_rate': str(rate) if rate is not None else None,
        'currency': currency, 'price_ht': cash(ht) if ht is not None else None,
        'promotion': promotion, 'usual_price': cash(usual) if usual is not None else None,
        'promotion_price': cash(price) if promotion and price is not None else None,
        'observed_at': observed.isoformat() if observed is not None else None,
        'status': 'rejected' if blocking else 'pending' if reasons else 'valid',
        'reasons': blocking + reasons, 'reviewable': not blocking and 'Relevé trop ancien' not in reasons,
    }
