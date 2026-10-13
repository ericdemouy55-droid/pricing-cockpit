import unittest
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook
from eurotyre.engine import demo, calculate
from eurotyre.exports import pricing_export_frame, excel_bytes, csv_bytes, PRICING_COLUMNS
from eurotyre.service import mutate


class CompactExportTests(unittest.TestCase):
    def test_saved_bf_discount_and_automatic_market_discount(self):
        state = mutate(demo(), 'bf_grid', 'pricing', changes=[{
            'brand': 'Michelin', 'season': 'Été', 'min': 16, 'max': 16, 'discount': '40'}])
        frame = pricing_export_frame(calculate(state), state['rules'])
        self.assertEqual(frame.columns.tolist(), PRICING_COLUMNS)
        self.assertEqual(len(frame), 68)
        row = frame.loc[frame['Code EAN'].eq('2000000000036')].iloc[0]
        self.assertEqual(row['Prix HT'], 70.08)
        self.assertEqual(row['Remise BF (%)'], 40)
        automatic = frame.loc[frame['Code EAN'].eq('2000000000006')].iloc[0]
        self.assertEqual(automatic['Prix HT'], 163)
        self.assertEqual(automatic['Remise BF (%)'], 37.5)

    def test_applied_discount_is_preserved_after_money_rounding(self):
        rows = [{'brand': 'Michelin', 'season': 'Été', 'ean': '0123456789012',
                 'bf': '1.45', 'market_price': '0.90', 'recommended': '0.91', 'rule': 'bf'}]
        rules = [{'id': 'bf', 'base': 'bf', 'discount': '37.50'}]
        frame = pricing_export_frame(rows, rules)
        self.assertEqual(frame.iloc[0]['Remise BF (%)'], 37.5)

    def test_excel_csv_keep_columns_leading_zero_ean_and_numeric_prices(self):
        rows = [{'brand': '=1+1', 'season': 'Été', 'ean': '0123456789012',
                 'bf': '116.80', 'market_price': '73.00', 'recommended': '70.08', 'rule': 'bf'}]
        frame = pricing_export_frame(rows, [{'id': 'bf', 'base': 'bf', 'discount': '40.00'}])
        book = load_workbook(BytesIO(excel_bytes(frame)))
        sheet = book.active
        self.assertEqual([c.value for c in sheet[1]], PRICING_COLUMNS)
        self.assertEqual(sheet['C2'].value, '0123456789012')
        self.assertEqual(sheet['C2'].number_format, '@')
        self.assertEqual(sheet['D2'].value, 70.08)
        self.assertEqual(sheet['D2'].number_format, '0.00')
        self.assertEqual(sheet['E2'].value, 40)
        self.assertNotEqual(sheet['A2'].data_type, 'f')
        csv = pd.read_csv(BytesIO(csv_bytes(frame)), sep=';', decimal=',', dtype={'Code EAN': str})
        self.assertEqual(csv.columns.tolist(), PRICING_COLUMNS)
        self.assertEqual(csv.iloc[0]['Code EAN'], '0123456789012')
        self.assertEqual(csv.iloc[0]['Prix HT'], 70.08)
        self.assertEqual(csv.iloc[0]['Remise BF (%)'], 40)

    def test_missing_prices_are_excluded_without_zero_substitution(self):
        row = {'brand': 'Michelin', 'season': 'Hiver', 'ean': '', 'bf': '100.00', 'rule': ''}
        frame = pricing_export_frame([{**row, 'recommended': v} for v in (None, '0', '-1', 'NaN')], [])
        self.assertTrue(frame.empty)
        self.assertEqual(frame.columns.tolist(), PRICING_COLUMNS)
        self.assertTrue(excel_bytes(frame))
        self.assertEqual(csv_bytes(frame).decode('utf-8-sig').strip(), ';'.join(PRICING_COLUMNS))


if __name__ == '__main__':
    unittest.main()
