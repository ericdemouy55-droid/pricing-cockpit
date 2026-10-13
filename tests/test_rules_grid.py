import unittest
from copy import deepcopy
from decimal import Decimal

from eurotyre.engine import demo, calculate, cash, DIAMETER_BANDS
from eurotyre.rules_grid import cell_key, market_discounts, saved_discounts
from eurotyre.service import mutate


def change(brand='Michelin', season='Été', low=16, high=16, discount=40):
    return {'brand': brand, 'season': season, 'min': low, 'max': high, 'discount': discount}


class BFGridTests(unittest.TestCase):
    def test_bf_price_override_and_clear_preserve_legacy_rules(self):
        original = demo()
        updated = mutate(original, 'bf_grid', 'pricing', changes=[change()])
        self.assertEqual(updated['rules'][:3], original['rules'])
        self.assertEqual(original['rules'], demo()['rules'])
        row = calculate(updated)[36]  # Michelin, été, 16 pouces, BF 116,80 / marché 73.
        self.assertEqual(row['recommended'], '70.08')
        self.assertEqual(row['variation'], '-4.00')
        self.assertEqual(row['delta'], '-2.92')
        self.assertFalse(row['alerts'])  # 40 % de remise BF ne déclenche pas le seuil marché 15 %.
        self.assertEqual(calculate(updated)[6]['recommended'], calculate(original)[6]['recommended'])
        cleared = mutate(updated, 'bf_grid', 'pricing', changes=[change(discount=None)])
        self.assertEqual(cleared['rules'], original['rules'])
        self.assertEqual(calculate(cleared)[36]['recommended'], '75.19')

    def test_zero_discount_and_actual_market_deviation(self):
        state = mutate(demo(), 'bf_grid', 'pricing', changes=[change(discount=0)])
        row = calculate(state)[36]
        self.assertEqual(row['recommended'], row['bf'])
        self.assertEqual(row['variation'], '60.00')
        self.assertIn('Écart marché excessif', row['alerts'])

    def test_bf_does_not_invent_market_but_can_price_without_it(self):
        state = demo()
        state['products'] = state['products'][36:37]
        state['market'] = []
        state = mutate(state, 'bf_grid', 'pricing', changes=[change()])
        row = calculate(state)[0]
        self.assertEqual(row['recommended'], '70.08')
        for field in ('market_price', 'delta', 'variation'):
            self.assertIsNone(row[field])
        self.assertIn('Prix marché absent', row['alerts'])
        state = mutate(state, 'version', 'pricing')
        with self.assertRaises(ValueError):
            mutate(state, 'validate', 'pricing', id='V1')

    def test_diameter_boundaries_and_decimal_rounding(self):
        state = demo()
        prototype = state['products'][36]
        state['products'] = [{**prototype, 'id': str(d), 'diameter': d, 'bf': '100.05'}
                             for d in (13, 14, 15, 16, 17, 18, 19, 30)]
        changes = [change(low=low, high=high, discount=i * 5)
                   for i, (_, low, high) in enumerate(DIAMETER_BANDS)]
        state = mutate(state, 'bf_grid', 'pricing', changes=changes)
        for row in calculate(state):
            index = next(i for i, (_, low, high) in enumerate(DIAMETER_BANDS)
                         if low <= row['diameter'] <= high)
            self.assertEqual(row['recommended'], cash(Decimal('100.05') * (1 - Decimal(index * 5) / 100)))

    def test_market_information_independent_of_rules(self):
        state = demo()
        expected = market_discounts(calculate(state))
        updated = mutate(state, 'bf_grid', 'pricing', changes=[change()])
        self.assertEqual(market_discounts(calculate(updated)), expected)
        state['rules'] = []
        self.assertEqual(market_discounts(calculate(state)), expected)
        self.assertEqual(expected[cell_key('Michelin', 'Été', 16, 16)], '37.50')
        # Prix marché manquants : aucun zéro ni référence de remplacement.
        self.assertNotIn(cell_key('Michelin', 'Été', 15, 15), expected)

    def test_grid_validation_atomicity_and_roles(self):
        state = demo()
        original = deepcopy(state)
        for invalid in (-1, 100, 'NaN', 'abc'):
            with self.assertRaises(ValueError):
                mutate(state, 'bf_grid', 'pricing', changes=[change(), change(low=17, high=17, discount=invalid)])
            self.assertEqual(state, original)
        for invalid in (change(low=14, high=16), change(brand='Unknown'), change(season='Summer')):
            with self.assertRaises(ValueError):
                mutate(state, 'bf_grid', 'pricing', changes=[invalid])
        with self.assertRaises(PermissionError):
            mutate(state, 'bf_grid', 'viewer', changes=[change()])
        with self.assertRaises(ValueError):
            mutate(state, 'bf_grid', 'pricing', changes=[change(), change()])
        updated = mutate(state, 'bf_grid', 'admin', changes=[change(discount='37,50')])
        self.assertEqual(saved_discounts(updated['rules'])[cell_key('Michelin', 'Été', 16, 16)], '37.50')

    def test_tiny_bf_and_invalid_bf_block(self):
        state = mutate(demo(), 'bf_grid', 'pricing', changes=[change(discount=99.99)])
        state['products'] = state['products'][36:37]
        state['products'][0]['bf'] = '0.01'
        row = calculate(state)[0]
        self.assertIsNone(row['recommended'])
        self.assertIn('PV nul après arrondi au centime', row['alerts'])
        state['products'][0]['bf'] = None
        self.assertIn('BF absent ou invalide', calculate(state)[0]['alerts'])


if __name__ == '__main__':
    unittest.main()
