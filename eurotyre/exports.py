from io import BytesIO
import pandas as pd
from .engine import demo
from .imports import LABELS

EXPORT = {'ean':'EAN', 'ref':'Référence produit', 'brand':'Marque', 'dimension':'Dimension', 'season':'Saison', 'bf':'Barème fournisseur HT', 'market_price':'Prix marché HT', 'variation':'Variation %', 'recommended':'Prix recommandé HT', 'validity':'Date de validité'}

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
        record['Version'] = safe_text(version['id'])
        records.append(record)
    return pd.DataFrame(records)

def excel_bytes(frame):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        frame.to_excel(writer, index=False, sheet_name='Prix recommandés')
        sheet = writer.sheets['Prix recommandés']
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(35, max(14, len(str(col[0].value)) + 3))
        sheet.freeze_panes = 'A2'
    return buf.getvalue()

def csv_bytes(frame):
    return frame.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')

def template(kind, anomalies=False):
    state = demo()
    # Default templates contain 36 fully matched products and realistic net costs.
    products = state['products'] if anomalies else state['products'][1:37]
    if kind == 'bf':
        rows = [{LABELS[k].replace(' (facultatif)', ''): p[k] for k in ('manufacturer', 'brand', 'ref', 'ean', 'dimension', 'load', 'speed', 'season', 'bf', 'net', 'validity')} for p in products]
        if not anomalies:
            for r in rows:
                r['PA net HT'] = str(round(float(r['Barème fournisseur HT']) / 1.6 * .66, 2))
    else:
        # Derive template prices only from the deliberately generated fictional dataset.
        prices = {p['ean']: str(round(float(p['bf']) / 1.6, 2)) for p in products}
        rows = [{LABELS[k]: p[k] for k in ('ean', 'ref', 'brand', 'dimension', 'load', 'speed', 'season')} | {'Prix marché HT': prices[p['ean']], 'Date collecte': '2026-10-13', 'Source': 'Données fictives de démonstration'} for p in products]
    return pd.DataFrame(rows)
