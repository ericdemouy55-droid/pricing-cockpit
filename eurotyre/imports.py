from io import BytesIO
import csv
import re
from datetime import datetime
from uuid import uuid4
from zipfile import ZipFile, BadZipFile
import pandas as pd
from .engine import norm, dimension, season, decimal, cash, parse_ean

FIELDS = {'bf': ['manufacturer', 'brand', 'ref', 'ean', 'dimension', 'width', 'height', 'diameter', 'load', 'speed', 'season', 'profile', 'xl', 'runflat', 'homologation', 'vehicle', 'bf', 'validity'], 'market': ['ean', 'ref', 'brand', 'dimension', 'width', 'height', 'diameter', 'load', 'speed', 'season', 'price', 'date', 'source']}
LABELS = {'manufacturer': 'Manufacturier', 'brand': 'Marque', 'ref': 'Référence fabricant', 'ean': 'EAN', 'dimension': 'Dimension', 'width': 'Largeur', 'height': 'Série / hauteur', 'diameter': 'Diamètre', 'load': 'Indice de charge', 'speed': 'Indice de vitesse', 'season': 'Saison', 'bf': 'Barème fournisseur HT', 'validity': 'Date de validité', 'price': 'Prix marché HT', 'date': 'Date collecte', 'source': 'Source'}
ALIASES = {'manufacturer': ['manufacturier', 'manufacturer', 'fournisseur'], 'brand': ['marque', 'brand'], 'ref': ['ref', 'reference', 'reference fabricant', 'reference produit'], 'ean': ['ean', 'code ean', 'gtin'], 'dimension': ['dimension', 'dimensions'], 'width': ['largeur', 'width'], 'height': ['serie', 'hauteur', 'height', 'serie / hauteur'], 'diameter': ['diametre', 'diametre jante', 'diameter'], 'load': ['indice de charge', 'load'], 'speed': ['indice de vitesse', 'speed'], 'season': ['saison', 'season'], 'bf': ['bf', 'bareme fournisseur ht', 'bareme', 'tarif ht'], 'validity': ['date validite', 'date de validite', 'validity'], 'price': ['prix marche ht', 'prix public ht', 'price'], 'date': ['date collecte', 'date de collecte', 'date'], 'source': ['source']}
LABELS.update(profile='Profil / gamme', xl='XL', runflat='Runflat', homologation='Homologation constructeur', vehicle='Type de véhicule')
ALIASES.update(profile=['profil', 'gamme', 'profile'], xl=['xl', 'renforce'], runflat=['runflat', 'run flat'], homologation=['homologation', 'homologation constructeur'], vehicle=['vehicule', 'type vehicule', 'vehicle', 'type de vehicule'])

def read_upload(data: bytes, filename: str, sheet=None):
    if len(data) > 5 * 1024 * 1024:
        raise ValueError('Fichier limité à 5 Mo.')
    if filename.lower().endswith('.xlsx'):
        try:
            with ZipFile(BytesIO(data)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError('Classeur décompressé trop volumineux.')
        except BadZipFile as e:
            raise ValueError('Fichier Excel invalide.') from e
        book = pd.ExcelFile(BytesIO(data), engine='openpyxl')
        names = book.sheet_names
        sheet = sheet or names[0]
        df = pd.read_excel(book, sheet_name=sheet, dtype=str, keep_default_na=False)
    elif filename.lower().endswith('.csv'):
        try:
            txt = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            txt = data.decode('cp1252')
        try:
            sep = csv.Sniffer().sniff(txt[:10000], delimiters=';,\t|').delimiter
        except csv.Error:
            sep = ';'
        df = pd.read_csv(BytesIO(txt.encode()), sep=sep, dtype=str, keep_default_na=False)
        names = []
    else:
        raise ValueError('Formats acceptés : XLSX et CSV.')
    if not 1 <= len(df) <= 10000:
        raise ValueError('Entre 1 et 10 000 lignes attendues.')
    if len(df.columns) > 100:
        raise ValueError('100 colonnes maximum.')
    return df, names

def guess(headers, kind):
    return {f: next((h for h in headers if norm(h) in ALIASES[f]), '') for f in FIELDS[kind]}

def iso_date(value):
    txt = str(value or '').strip()
    if not txt:
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Date invalide (AAAA-MM-JJ ou JJ/MM/AAAA).')

def import_rows(rows, mapping, kind):
    if kind not in FIELDS:
        raise ValueError('Type de référentiel inconnu.')
    if not 1 <= len(rows) <= 10000:
        raise ValueError('Entre 1 et 10 000 lignes attendues.')
    result, errors, seen = [], [], set()
    for i, row in enumerate(rows, 2):
        def get(field):
            value = row.get(mapping.get(field, ''), '')
            return str(value if value is not None else '').strip()
        try:
            ean, ref, brand = parse_ean(get('ean')), get('ref'), get('brand')
            dim = dimension(get('dimension'))
            if not dim and all(get(f) for f in ('width', 'height', 'diameter')):
                dim = dimension(f"{get('width')}/{get('height')}R{get('diameter')}")
            seas, load, speed = season(get('season')), get('load'), get('speed').upper()
            price = decimal(get('bf' if kind == 'bf' else 'price'))
            if ean and not re.fullmatch(r'\d{13}', ean):
                raise ValueError('EAN : 13 chiffres attendus.')
            if not brand or not dim or not seas:
                raise ValueError('Marque, dimension ou saison invalide.')
            if not ean and not ref and not (load and speed):
                raise ValueError('Sans EAN/référence, charge et vitesse obligatoires.')
            if price is None or price <= 0 or price > 100000:
                raise ValueError('Prix HT positif (maximum 100 000 €) requis.')
            if decimal(cash(price)) <= 0:
                raise ValueError('Prix HT nul après arrondi au centime.')
            date = iso_date(get('validity' if kind == 'bf' else 'date'))
            key = ('ean', ean) if ean else ('tech', norm(brand), ref or dim, load, speed, seas)
            if key in seen:
                raise ValueError('Doublon dans le fichier.')
            seen.add(key)
            common = {'ean': ean, 'ref': ref, 'brand': brand, 'dimension': dim, 'load': load, 'speed': speed, 'season': seas}
            if kind == 'bf':
                def flag(field):
                    value = norm(get(field))
                    if not value:
                        return None
                    if value in ('oui', 'yes', 'true', '1'):
                        return True
                    if value in ('non', 'no', 'false', '0'):
                        return False
                    raise ValueError(f'{LABELS[field]} : oui/non requis.')
                result.append(common | {'id': str(uuid4()), 'manufacturer': get('manufacturer') or brand, 'diameter': int(dim.split('R')[1]), 'bf': cash(price), 'validity': date,
                    'profile': get('profile'), 'xl': flag('xl'), 'runflat': flag('runflat'), 'homologation': get('homologation'), 'vehicle': get('vehicle')})
            else:
                result.append(common | {'price': cash(price), 'date': date, 'source': get('source') or 'Fichier fourni'})
        except ValueError as e:
            errors.append(f'Ligne {i} : {e}')
    return result, errors

