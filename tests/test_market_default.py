import unittest
from copy import deepcopy

from eurotyre.engine import demo, calculate, market_discount_reference, market_group
from eurotyre.exports import pricing_export_frame
from eurotyre.rules_grid import market_discounts, cell_key
from eurotyre.service import mutate


def scenario(items):
    state = demo()
    prototype = state['products'][36]
    state['products'], state['market'] = [], []
    state['settings']['max_deviation'] = 100
    for i, item in enumerate(items):
        product = {**prototype, 'id': str(i), 'ean': f'2000001{i:06}', 'ref': f'TEST-{i}',
                   'bf': item.get('bf', '100.00'), 'diameter': item.get('diameter', 16),
                   'brand': item.get('brand', 'Michelin'), 'season': item.get('season', 'Été'),
                   'load': item.get('load', '94'), 'speed': item.get('speed', 'V')}
        product['dimension'] = f'195/55 R{product["diameter"]}'
        state['products'].append(product)
        if item.get('market') is not None:
            state['market'].append({k: product[k] for k in ('ean', 'ref', 'brand', 'dimension', 'load', 'speed', 'season')}
                                   | {'price': item['market'], 'date': '2026-10-13', 'source': 'Test fictif'})
    return state


class AutomaticMarketDiscountTests(unittest.TestCase):
    def test_empty_cells_align_each_ean_and_group_mean_is_information_only(self):
        state = scenario([
            {'market': '50.00'},  # 50 %
            {'brand': 'MICHELIN', 'bf': '200.00', 'market': '160.00'},  # 20 %
            {'season': 'Hiver', 'market': '90.00'},
            {'diameter': 17, 'market': '95.00'},
            {'brand': 'Continental', 'market': '80.00'},
        ])
        rows = calculate(state)
        self.assertEqual([r['applied_discount'] for r in rows], ['50.00', '20.00', '10.00', '5.00', '20.00'])
        self.assertEqual([r['recommended'] for r in rows], ['50.00', '160.00', '90.00', '95.00', '80.00'])
        self.assertTrue(all(r['discount_source'] == 'market' for r in rows))
        self.assertEqual(market_discounts(rows)[cell_key('Michelin', 'Été', 16, 16)], '35.00')

    def test_empty_cells_never_share_another_eans_market_price(self):
        state = scenario([{'diameter': 13, 'market': '95.00'}, {'diameter': 14, 'market': '65.00'},
                          {'diameter': 19, 'market': '90.00'}, {'diameter': 30, 'market': '50.00'}])
        self.assertEqual([r['applied_discount'] for r in calculate(state)], ['5.00', '35.00', '10.00', '50.00'])

    def test_missing_reference_is_excluded_even_when_group_mean_exists(self):
        state = scenario([{'market': '66.66'}, {'market': '66.65'}, {'bf': '1.45', 'load': '96'}])
        rows = calculate(state)
        self.assertEqual(market_discount_reference(rows)[market_group('Michelin', 'Été', 16)], '33.35')
        self.assertIsNone(rows[2]['recommended'])
        self.assertIsNone(rows[2]['applied_discount'])
        self.assertEqual(pricing_export_frame(rows, state['rules'])['Prix HT'].tolist(), [66.66, 66.65])
        self.assertIsNone(rows[2]['market_price'])
        self.assertIn('Prix marché absent', rows[2]['alerts'])

    def test_no_reference_means_no_default_price_but_explicit_zero_still_works(self):
        state = scenario([{}])
        row = calculate(state)[0]
        self.assertIsNone(row['recommended'])
        self.assertIsNone(row['applied_discount'])
        self.assertIn('Remise marché indisponible', row['alerts'])
        state = mutate(state, 'bf_grid', 'pricing', changes=[{
            'brand':'Michelin', 'season':'Été', 'min':16, 'max':16, 'discount':0}])
        row = calculate(state)[0]
        self.assertEqual(row['recommended'], '100.00')
        self.assertEqual(row['applied_discount'], '0.00')
        self.assertEqual(row['discount_source'], 'bf')

    def test_zero_and_negative_market_discounts_are_not_empty(self):
        state = scenario([{'market':'100.00'}, {'season':'Hiver', 'market':'110.00'}])
        self.assertEqual([r['applied_discount'] for r in calculate(state)], ['0.00', '-10.00'])
        self.assertEqual([r['recommended'] for r in calculate(state)], ['100.00', '110.00'])

    def test_archived_versions_keep_their_prices_and_applied_market_rate(self):
        state = scenario([{'market':'50.00'}, {'market':'80.00'}])
        state['rules'].append({**state['rules'][0], 'id':'old duplicate'})
        state = mutate(state, 'version', 'pricing')
        state = mutate(state, 'validate', 'pricing', id='V1')
        archived = deepcopy(state['versions'][0])
        self.assertEqual(archived['rules'], [])  # Anciennes variations hors calcul courant.
        state = mutate(state, 'bf_grid', 'pricing', changes=[{
            'brand':'Michelin', 'season':'Été', 'min':16, 'max':16, 'discount':40}])
        self.assertEqual(state['versions'][0], archived)
        self.assertEqual(calculate(state)[0]['recommended'], '60.00')
        self.assertEqual(pricing_export_frame(archived['rows'], archived['rules']).iloc[0]['Prix HT'], 50)
        self.assertEqual(pricing_export_frame(archived['rows'], archived['rules']).iloc[0]['Remise BF (%)'], 50)


if __name__ == '__main__':
    unittest.main()
