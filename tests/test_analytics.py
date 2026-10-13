import unittest
from decimal import Decimal
from eurotyre.analytics import price_indicators, summarize

def row(bf, market, retailer, brand='Michelin', season='Été'):
    return dict(bf=bf, market_price=market, recommended=retailer, brand=brand, season=season)

class AnalyticsTests(unittest.TestCase):
    def test_reference_percentages_and_sign(self):
        result = price_indicators(row('100', '80', '84'))
        self.assertEqual(result, dict(market_discount=Decimal('20'),
                                     retailer_discount=Decimal('16'), market_gap=Decimal('5')))
        result = price_indicators(row('100', '120', '108'))
        self.assertEqual(result['market_discount'], Decimal('-20'))
        self.assertEqual(result['retailer_discount'], Decimal('-8'))
        self.assertEqual(result['market_gap'], Decimal('-10'))

    def test_mean_of_percentages_on_identical_references(self):
        rows = [row('100', '80', '84'), row('200', '100', '90'),
                row('100', '50', None), row('100', None, '70')]
        result = summarize(rows)[0]
        self.assertEqual(result['references'], 4)
        self.assertEqual(result['compared'], 2)
        self.assertEqual(result['market_discount'], '35.00')
        self.assertEqual(result['retailer_discount'], '35.50')
        self.assertEqual(result['market_gap'], '-2.50')

    def test_brand_and_season_groups(self):
        rows = [row('100', '80', '84'), row('100', '80', '76', brand='MICHELIN', season='Hiver'),
                row('100', '80', '80', brand='Continental')]
        seasons = summarize(rows)
        self.assertEqual([(g['brand'], g['season']) for g in seasons],
                         [('Continental', 'Été'), ('Michelin', 'Été'), ('MICHELIN', 'Hiver')])
        brands = summarize(rows, by_season=False)
        self.assertEqual(len(brands), 2)
        self.assertEqual(brands[1]['compared'], 2)
        self.assertEqual(brands[1]['market_gap'], '0.00')

    def test_missing_invalid_and_empty_data(self):
        self.assertEqual(summarize([]), [])
        for value in (None, '0', '-1', 'NaN', 'Infinity'):
            result = summarize([row(value, '80', '84')])[0]
            self.assertEqual(result['compared'], 0)
            self.assertIsNone(result['market_discount'])
            self.assertIsNone(result['retailer_discount'])
            self.assertIsNone(result['market_gap'])

    def test_round_only_after_averaging(self):
        result = summarize([row('300', '299.99', '299.99'), row('300', '299.99', '299.99'),
                            row('300', '299.96', '299.96')])[0]
        # Arrondir d'abord donne (0.00 + 0.00 + 0.01) / 3, soit 0.00 %.
        # La moyenne précise de 0.006666... % doit rester 0.01 %.
        self.assertEqual(result['market_discount'], '0.01')
        self.assertEqual(result['retailer_discount'], '0.01')

if __name__ == '__main__': unittest.main()
