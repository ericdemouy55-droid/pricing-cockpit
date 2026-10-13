from io import BytesIO
import pandas as pd
from .engine import demo, decimal, cash
from .imports import LABELS
from .analytics import price_indicators

EXPORT = {'ean':'EAN', 'ref':'Référence produit', 'brand':'Marque', 'dimension':'Dimension', 'season':'Saison', 'bf':'Barème fournisseur HT', 'market_price':'Prix marché HT', 'variation':'Variation %', 'recommended':'Prix commerçant Eurotyre HT', 'validity':'Date de validité'}
PRICING_COLUMNS = ['Marque', 'Saison', 'Code EAN', 'Prix HT', 'Remise BF (%)']

def safe_text(value):
    text = str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text

def export_frame(version):
    if version['status'] not in ('Validée', 'Publiée'):
        raise ValueError('Une version validée est requise pour exporter.')
    records = []
    numeric = {'bf', 'market_price', 'variation', 'recommended'}
    for row in version['rows']:
        record = {label: float(row[key]) if key in numeric and row[key] is not None else safe_text(row.get(key)) for key, label in EXPORT.items()}
        for name, label in (('market_discount', 'Remise marché / BF (%)'),
                            ('retailer_discount', 'Remise commerçant / BF (%)'),
                            ('market_gap', 'Écart commerçant / marché (%)')):
            value = price_indicators(row)[name]
            record[label] = float(value) if value is not None else None
        record['Version'] = safe_text(version['id'])
        records.append(record)
    return pd.DataFrame(records)

def pricing_export_frame(rows, rules):
    """Tarif compact : prix Eurotyre calculés et remise BF appliquée ou équivalente."""
    by_id = {rule['id']: rule for rule in rules}
    records = []
    for row in rows:
        price = decimal(row.get('recommended'))
        if price is None or price <= 0:
            continue
        rule = by_id.get(row.get('rule'), {})
        discount = decimal(row.get('applied_discount'))
        if discount is None:  # Compatibilité des instantanés créés avant ce champ.
            discount = decimal(rule.get('discount')) if rule.get('base') == 'bf' else price_indicators(row)['retailer_discount']
        records.append({
            'Marque': safe_text(row.get('brand')),
            'Saison': safe_text(row.get('season')),
            'Code EAN': safe_text(row.get('ean')),
            'Prix HT': float(cash(price)),
            'Remise BF (%)': float(cash(discount)) if discount is not None else None,
        })
    return pd.DataFrame(records, columns=PRICING_COLUMNS)

def excel_bytes(frame):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        frame.to_excel(writer, index=False, sheet_name='Prix recommandés')
        sheet = writer.sheets['Prix recommandés']
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(35, max(14, len(str(col[0].value)) + 3))
            if col[0].value in ('Code EAN', 'Prix HT', 'Remise BF (%)'):
                for cell in col[1:]:
                    cell.number_format = '@' if col[0].value == 'Code EAN' else '0.00'
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
    return buf.getvalue()

def csv_bytes(frame):
    return frame.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')

def template(kind, anomalies=False):
    state = demo()
    # Default templates contain 36 fully matched fictional products.
    products = state['products'] if anomalies else state['products'][1:37]
    if kind == 'bf':
        rows = [{LABELS[k]: p[k] for k in ('manufacturer', 'brand', 'ref', 'ean', 'dimension', 'load', 'speed', 'season', 'bf', 'validity')} for p in products]
    else:
        # Derive template prices only from the deliberately generated fictional dataset.
        prices = {p['ean']: str(round(float(p['bf']) / 1.6, 2)) for p in products}
        rows = [{LABELS[k]: p[k] for k in ('ean', 'ref', 'brand', 'dimension', 'load', 'speed', 'season')} | {'Prix marché HT': prices[p['ean']], 'Date collecte': '2026-10-13', 'Source': 'Données fictives de démonstration'} for p in products]
    return pd.DataFrame(rows)

