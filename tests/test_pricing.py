import unittest
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import tempfile
from pathlib import Path
import pandas as pd
from eurotyre.engine import demo, cash, calculate, dimension, parse_rule, rule_conflicts, priority
from eurotyre.imports import import_rows, read_upload, guess
from eurotyre.service import mutate
from eurotyre.storage import SQLiteStore, ConflictError
from eurotyre.exports import template, excel_bytes, csv_bytes, export_frame

class PricingTests(unittest.TestCase):
    def test_dimensions(self):
        for txt in ('225/45R18 95Y', '225 / 45 R 18', '225/45ZR18', '2254518'):
            self.assertEqual(dimension(txt), '225/45 R18')
        self.assertEqual(dimension('999/45R18'), '')
        self.assertEqual(cash('10.005'), '10.01')

    def test_legacy_variations_do_not_override_empty_bf_cells(self):
        s = demo(); s['products'] = s['products'][1:2]
        for pct in (5, -3, 0):
            s['rules'] = [parse_rule({'id':'test','variation':pct})]
            r = calculate(s)[0]
            self.assertEqual(r['recommended'], r['market_price'])
            self.assertEqual(r['applied_discount'], '37.50')
            self.assertEqual(r['discount_source'], 'market')

    def test_priority(self):
        s = demo(); s['products'] = s['products'][1:2]; p = s['products'][0]
        s['rules'] = [parse_rule({'id':'g','variation':1}), parse_rule({'id':'b','brand':p['brand'],'variation':2}), parse_rule({'id':'bs','brand':p['brand'],'season':p['season'],'variation':3}), parse_rule({'id':'bd','brand':p['brand'],'min':p['diameter'],'max':p['diameter'],'variation':4}), parse_rule({'id':'bds','brand':p['brand'],'min':p['diameter'],'max':p['diameter'],'season':p['season'],'variation':5})]
        for name in ('bds','bd','bs','b','g'):
            self.assertEqual(max(s['rules'], key=priority)['id'], name); s['rules'].pop()
        bf = parse_rule({'id':'bf', 'base':'bf', 'discount':40, 'brand':p['brand'],
                         'min':p['diameter'], 'max':p['diameter'], 'season':p['season']})
        s['rules'] = [parse_rule({'id':'general','variation':50}), bf]
        self.assertEqual(calculate(s)[0]['rule'], 'bf')
        self.assertEqual(calculate(s)[0]['recommended'], '75.84')

    def test_overlap_and_ambiguity(self):
        s = demo(); s['rules'].append({**s['rules'][0],'id':'dup'})
        self.assertTrue(rule_conflicts(s['rules']))
        self.assertNotIn('Conflit de règles', calculate(s)[1]['alerts'])
        bf = parse_rule({'id':'bf', 'base':'bf', 'discount':40, 'brand':'Continental',
                         'min':16, 'max':16, 'season':'Été'})
        s['rules'] += [bf, {**bf, 'id':'bf duplicate'}]
        self.assertIn('Conflit de règles', calculate(s)[1]['alerts'])
        self.assertIsNone(calculate(s)[1]['recommended'])
        s = demo(); s['market'].append(deepcopy(s['market'][0]))
        self.assertIn('Correspondance ambiguë', calculate(s)[1]['alerts'])
        self.assertIsNone(calculate(s)[0]['recommended'])

    def test_ean_and_fallback(self):
        s = demo(); s['products'] = s['products'][1:2]
        self.assertEqual(calculate(s)[0]['match'], 'EAN')
        s['products'][0]['ean'] = ''
        self.assertEqual(calculate(s)[0]['match'], 'Caractéristiques')
        s['market'][0]['ref'] = ''; s['market'][0]['speed'] = 'W'
        self.assertIsNone(calculate(s)[0]['market_price'])

    def test_prices_ignore_legacy_cost_fields(self):
        s = demo(); expected = calculate(s)[1]
        s['products'][1]['net'] = '99999.00'
        s['settings']['min_margin'] = 99
        actual = calculate(s)[1]
        self.assertEqual(actual, expected)
        self.assertFalse({'net', 'margin', 'margin_eur', 'markup'} & actual.keys())

    def test_actual_formats_and_templates(self):
        for kind in ('bf', 'market'):
            frame = template(kind)
            for data, name in ((excel_bytes(frame), 'a.xlsx'), (csv_bytes(frame), 'b.csv')):
                df, _ = read_upload(data, name)
                rows, errors = import_rows(df.to_dict('records'), guess(df.columns,kind), kind)
                self.assertFalse(errors, errors)
                self.assertEqual(len(rows), 36)
                self.assertEqual(len(rows[0]['ean']), 13)

    def test_mapping_invalid_rows_atomic(self):
        raw = [{'A':'Michelin','B':'205/55R16','C':'summer','D':'100,25','E':'2000000000001'}]
        mapping = dict(brand='A',dimension='B',season='C',bf='D',ean='E')
        rows, errors = import_rows(raw,mapping,'bf'); self.assertFalse(errors); self.assertEqual(rows[0]['bf'],'100.25')
        _, errors = import_rows(raw+raw,mapping,'bf'); self.assertEqual(len(errors),1)
        old = demo()
        with self.assertRaises(ValueError): mutate(old,'import','admin',rows=raw+raw,mapping=mapping,kind='bf',name='test')
        self.assertEqual(len(old['products']),72)

    def test_separate_dimension_columns(self):
        raw = [{'brand':'Michelin','w':'205','h':'55','d':'16','season':'été','price':'100','ean':'2000000000001'}]
        mapping = dict(brand='brand',width='w',height='h',diameter='d',season='season',bf='price',ean='ean')
        rows, errors = import_rows(raw,mapping,'bf'); self.assertFalse(errors); self.assertEqual(rows[0]['dimension'],'205/55 R16')

    def test_import_rejects_amounts_rounded_to_zero(self):
        mapping = dict(brand='brand', dimension='dim', season='season',
                       ean='ean', bf='price', price='price')
        row = dict(brand='Michelin', dim='205/55R16', season='été',
                   ean='2000000000001', price='0.004')
        for kind in ('bf', 'market'):
            rows, errors = import_rows([row], mapping, kind)
            self.assertFalse(rows)
            self.assertTrue(any('arrondi' in e for e in errors))
        rows, errors = import_rows([{**row, 'price':'0.005'}], mapping, 'bf')
        self.assertFalse(errors)
        self.assertEqual(rows[0]['bf'], '0.01')

    def test_zero_rounded_price_blocks_without_crash(self):
        s = demo(); s['products'] = s['products'][1:2]
        s['products'][0]['bf'] = '0.01'
        s['rules'] = [parse_rule({'id':'discount', 'base':'bf', 'discount':99.99,
                                 'brand':'Continental', 'min':16, 'max':16, 'season':'Été'})]
        s['market'][0]['price'] = '0.01'
        result = calculate(s)[0]
        self.assertIsNone(result['recommended'])
        self.assertTrue(any('PV nul' in a for a in result['alerts']))
        s['rules'] = []
        s['products'][0]['net'] = '0.00'
        result = calculate(s)[0]
        self.assertFalse(result['alerts'])
        self.assertNotIn('net', result)

    def test_permissions(self):
        with self.assertRaises(PermissionError): mutate(demo(),'version','viewer')
        with self.assertRaises(PermissionError): mutate(demo(),'import','pricing')

    def test_snapshot_validation_and_exports(self):
        s = demo()
        s = mutate(s,'version','pricing')
        with self.assertRaises(ValueError): mutate(s,'validate','pricing',id='V1')
        with self.assertRaises(ValueError): export_frame(s['versions'][0])
        for kind in ('bf','market'):
            frame = template(kind)
            s = mutate(s,'import','admin',rows=frame.to_dict('records'),mapping=guess(frame.columns,kind),kind=kind,name='demo')
        self.assertEqual(len(s['imports']),2)
        self.assertFalse(any(r['alerts'] for r in calculate(s)))
        s = mutate(s,'version','pricing');s = mutate(s,'validate','pricing',id='V2');s = mutate(s,'publish','pricing',id='V2')
        version = s['versions'][0]
        df = export_frame(version)
        out = pd.read_excel(BytesIO(excel_bytes(df)),dtype={'EAN':str})
        self.assertEqual(len(out),36);self.assertEqual(out.EAN.tolist(),df.EAN.tolist())
        self.assertEqual(s['versions'][1]['status'],'Brouillon')

    def test_persistence_and_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.db'; store = SQLiteStore(path); s = store.load()
            saved = store.save(mutate(s,'baseline','pricing'),s['revision'])
            self.assertEqual(SQLiteStore(path).load()['revision'],saved['revision'])
            with self.assertRaises(ConflictError): store.save(s,s['revision'])

if __name__ == '__main__': unittest.main()

