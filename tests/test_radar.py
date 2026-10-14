"""Tests utilisant exclusivement des produits et des réponses de flux fictifs."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock
import unittest
import pandas as pd
from openpyxl import load_workbook
from eurotyre.engine import calculate, empty_state, demo, parse_rule
from eurotyre.imports import import_rows, FIELDS, read_upload
from eurotyre.exports import csv_bytes, excel_bytes, pricing_export_frame
from eurotyre.service import mutate
from eurotyre.radar import settings, RETAILERS
from eurotyre.radar.catalog import demo_catalog, select_pilot, eligible_catalog, fingerprint, valid_ean
from eurotyre.radar.matching import match_candidate
from eurotyre.radar.prices import normalize
from eurotyre.radar.storage import SQLiteRadarStore
from eurotyre.radar.connectors import FileConnector, DisabledConnector, AuthorizedFeedConnector
from eurotyre.radar.pipeline import collect
from eurotyre.radar.market import summary, history_metrics, comparison_frame

NOW = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)


def configuration(products):
    config = settings({})
    config.update(enabled=True, selected_eans=[p['ean'] for p in products],
                  centers={n: 'CENTRE FICTIF' for n in RETAILERS})
    return config


def quote(product, price='60', **changes):
    candidate = {k: product.get(k) for k in ('ean', 'ref', 'brand', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat', 'homologation')}
    candidate.update(url='https://simulation.invalid/' + product['ean'], price=price,
        price_type='HT', currency='EUR', tax_rate='20', nature='pneu_seul',
        mounting_included=False, delivery_included=False, member_only=False, conditional_price=False,
        promotion=False, promotion_conditions='', observed_at=NOW.isoformat(),
        zone='Compiègne', center='CENTRE FICTIF')
    candidate.update(changes)
    return candidate


class CatalogAndMatchingTests(unittest.TestCase):
    def test_selection_of_200_is_unique_deterministic_and_covers_existing_groups(self):
        products = demo_catalog(400)
        selected = select_pilot(products)
        self.assertEqual(len(selected), 200)
        self.assertEqual(len({p['ean'] for p in selected}), 200)
        self.assertTrue(all(valid_ean(p['ean']) for p in selected))
        self.assertEqual([p['ean'] for p in selected], [p['ean'] for p in select_pilot(list(reversed(products)))])
        self.assertEqual(len({p['brand'] for p in selected}), 7)
        self.assertEqual(len({p['season'] for p in selected}), 3)
        self.assertTrue({13, 14, 15, 16, 17, 18, 19}.issubset({p['diameter'] for p in selected}))
        self.assertEqual({p['vehicle'] for p in selected}, {'Tourisme', 'SUV', 'VUL'})

    def test_invalid_ean_and_duplicate_ean_are_excluded_not_silently_deduplicated(self):
        products = demo_catalog(3)
        bad = {**products[2], 'ean': products[2]['ean'][:-1] + str((int(products[2]['ean'][-1]) + 1) % 10)}
        eligible, issues = eligible_catalog([products[0], {**products[0], 'profile': 'AUTRE PNEU'}, products[1], bad])
        self.assertEqual([p['ean'] for p in eligible], [products[1]['ean']])
        self.assertEqual(len(issues), 3)
        with self.assertRaises(ValueError):
            select_pilot(products, manual=[products[0]['ean']] * 2)
        with self.assertRaises(ValueError):
            select_pilot(products, manual=['0000000000001'])

    def test_200_real_format_rows_import_without_losing_attributes_or_ean(self):
        products = demo_catalog()
        frame = pd.DataFrame(products)
        loaded, _ = read_upload(excel_bytes(frame), 'test_fictif.xlsx')
        imported, errors = import_rows(loaded.to_dict('records'), {k: k for k in FIELDS['bf']}, 'bf')
        self.assertFalse(errors)
        self.assertEqual(len(imported), 200)
        self.assertEqual(imported[0]['ean'], products[0]['ean'])
        self.assertEqual(imported[0]['profile'], products[0]['profile'])
        self.assertIs(imported[0]['runflat'], False)
        self.assertEqual(len(select_pilot(imported)), 200)

    def test_exact_ean_and_unique_manufacturer_reference_are_automatic(self):
        products = demo_catalog(3)
        exact = match_candidate(products, quote(products[0]))
        self.assertEqual((exact['status'], exact['quality']), ('valid', 100))
        by_ref = match_candidate(products, quote(products[0], ean=''))
        self.assertEqual((by_ref['status'], by_ref['quality']), ('valid', 95))

    def test_same_ean_never_overrides_conflicting_identity(self):
        product = demo_catalog(1)[0]
        for changes in ({'load': '110'}, {'speed': 'H'}, {'season': 'Hiver'}, {'xl': True},
                        {'runflat': True}, {'profile': 'AUTRE PROFIL'}, {'brand': 'AUTRE MARQUE'}, {'homologation': 'AO'}):
            with self.subTest(changes=changes):
                self.assertEqual(match_candidate([product], quote(product, **changes))['status'], 'rejected')
        self.assertNotEqual(fingerprint(product), fingerprint({**product, 'xl': None}))

    def test_technical_match_is_pending_and_ambiguity_is_rejected(self):
        products = demo_catalog(2)
        candidate = quote(products[0], ean='', ref='')
        self.assertEqual(match_candidate(products, candidate)['status'], 'pending')
        duplicate = {**products[0], 'ean': products[1]['ean'], 'id': 'SECOND PNEU'}
        self.assertEqual(match_candidate([products[0], duplicate], candidate)['status'], 'rejected')
        self.assertEqual(match_candidate(products, {**candidate, 'profile': ''})['status'], 'rejected')


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.product = demo_catalog(1)[0]

    def test_ttc_ht_decimal_and_retained_original(self):
        result = normalize(quote(self.product, '119.99', price_type='TTC'), NOW)
        self.assertEqual(result['price_ht'], '99.99')
        self.assertEqual(result['price_original'], '119.99')
        self.assertEqual(result['tax_rate'], '20')
        self.assertEqual(result['status'], 'valid')

    def test_composition_unknown_member_prices_and_invalid_prices_never_feed_market(self):
        cases = [{'nature': 'montage_inclus'}, {'mounting_included': True}, {'delivery_included': ''},
                 {'member_only': True}, {'conditional_price': True}, {'promotion': ''},
                 {'price': 0}, {'price': -10}, {'price': 'NaN'}, {'currency': 'USD'},
                 {'observed_at': '2026-10-14'}, {'price_type': 'TTC', 'tax_rate': ''},
                 {'promotion': True, 'promotion_conditions': ''}, {'usual_price': '100'}]
        for changes in cases:
            with self.subTest(changes=changes):
                result = normalize(quote(self.product, **changes), NOW)
                self.assertEqual(result['status'], 'rejected')
                self.assertFalse(result['reviewable'])

    def test_future_stale_and_unusual_variations_are_controlled(self):
        self.assertEqual(normalize(quote(self.product, observed_at=(NOW + timedelta(hours=1)).isoformat()), NOW)['status'], 'rejected')
        stale = normalize(quote(self.product, observed_at=(NOW - timedelta(days=8)).isoformat()), NOW)
        self.assertEqual(stale['status'], 'pending')
        self.assertFalse(stale['reviewable'])
        changed = normalize(quote(self.product, '100'), NOW, {'price_ht': '60'})
        self.assertEqual(changed['status'], 'pending')
        self.assertTrue(changed['reviewable'])


class PersistentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + '/test-fictif.sqlite'
        self.database = SQLiteRadarStore(self.path)
        self.products = demo_catalog(2)
        self.config = configuration(self.products)

    def tearDown(self):
        self.temp.cleanup()

    def ingest(self, retailer='Norauto', records=None, now=NOW, simulated=False):
        return collect(self.products, [FileConnector(retailer, records or [quote(self.products[0])], 'TEST FICTIF', simulated)], self.database, self.config, now=now)

    def test_daily_identical_prices_persist_and_missing_is_not_zero(self):
        self.ingest()
        tomorrow = NOW + timedelta(days=1)
        self.ingest(records=[quote(self.products[0], observed_at=tomorrow.isoformat())], now=tomorrow)
        reopened = SQLiteRadarStore(self.path)
        observations = reopened.observations()
        self.assertEqual(len(observations), 4)
        valid = [o for o in observations if o['status'] == 'valid']
        self.assertEqual([o['price_ht'] for o in valid], ['60.00', '60.00'])
        self.assertTrue(all(o['price_ht'] is None for o in observations if o['status'] == 'missing'))
        self.assertEqual(len(reopened.runs()), 2)
        self.assertEqual(reopened.observations('AUTRE ESPACE'), [])

    def test_one_connector_error_never_interrupts_other_sources(self):
        broken = MagicMock(name='connecteur-fictif-en-erreur')
        broken.name = 'Norauto'
        broken.fetch.side_effect = RuntimeError('test error')
        good = FileConnector('Euromaster', [quote(self.products[0])], 'TEST FICTIF')
        report = collect(self.products, [broken, good, DisabledConnector('Feu Vert'), DisabledConnector('First Stop')], self.database, self.config, now=NOW)
        self.assertEqual([c['status'] for c in report['connectors']], ['error', 'completed', 'disabled', 'disabled'])
        self.assertEqual(report['connectors'][1]['valid'], 1)
        self.assertEqual(len(self.database.runs()), 1)

    def test_duplicate_offers_and_wrong_centers_do_not_contribute(self):
        self.ingest(records=[quote(self.products[0]), quote(self.products[0], '80')])
        self.assertFalse(any(o['status'] == 'valid' for o in self.database.observations()))
        self.ingest('Euromaster', [quote(self.products[0], center='AUTRE CENTRE')])
        prices = summary(self.products, self.database.observations(), self.config, now=NOW)
        self.assertIsNone(prices[self.products[0]['ean']]['reference'])

    def test_review_is_separate_from_original_and_validated_mapping_is_rechecked(self):
        candidate = quote(self.products[0], ean='', ref='')
        self.ingest(records=[candidate])
        pending = next(o for o in self.database.observations() if o['status'] == 'pending')
        self.database.review(pending['id'], True, 'TESTEUR FICTIF', 'Identité vérifiée sur les attributs')
        self.assertEqual(next(o for o in self.database.observations() if o['id'] == pending['id'])['status'], 'valid')
        with sqlite3.connect(self.path) as con:
            original = json.loads(con.execute('SELECT payload FROM radar_observation WHERE id=?', (pending['id'],)).fetchone()[0])
            self.assertEqual(original['status'], 'pending')
        self.ingest(records=[candidate])
        self.assertEqual(self.database.runs()[0]['connectors'][0]['valid'], 1)
        changed = {**candidate, 'xl': not candidate['xl']}
        self.ingest(records=[changed])
        self.assertFalse(any(o.get('status') == 'valid' and o['run_id'] == self.database.runs()[0]['id'] for o in self.database.observations()))
        self.database.review(pending['id'], False, 'TESTEUR', 'Annulation motivée')
        self.assertEqual(self.database.mappings('Norauto'), [])

    def test_forced_validation_of_incompatible_quote_is_blocked(self):
        self.ingest(records=[quote(self.products[0], nature='montage_inclus')])
        rejected = next(o for o in self.database.observations() if o['status'] == 'rejected')
        with self.assertRaises(ValueError):
            self.database.review(rejected['id'], True, 'TEST', 'Tentative invalide')

    def test_feed_tokens_are_never_retained(self):
        self.ingest(records=[quote(self.products[0], token='SECRET-TEST', api_key='SECRET-TEST')])
        self.assertNotIn('SECRET-TEST', json.dumps(self.database.observations()))

    def test_unknown_observation_date_is_not_replaced_with_collection_date(self):
        self.ingest(records=[quote(self.products[0], observed_at='')])
        rejected = next(o for o in self.database.observations() if o['status'] == 'rejected')
        self.assertIsNone(rejected['observed_at'])
        with sqlite3.connect(self.path) as con:
            date, collected = con.execute('SELECT observed_at,collected_at FROM radar_observation WHERE id=?', (rejected['id'],)).fetchone()
            self.assertIsNone(date)
            self.assertEqual(collected, NOW.isoformat())

    def test_median_count_freshness_promotions_and_external_fallback(self):
        for retailer, price in zip(RETAILERS, ('60', '80', '100', '120')):
            self.ingest(retailer, [quote(self.products[0], price)])
        prices = summary(self.products, self.database.observations(), self.config, now=NOW)
        first = prices[self.products[0]['ean']]
        self.assertEqual((first['reference'], first['count'], first['min'], first['max']), ('90.00', 4, '60.00', '120.00'))
        self.assertEqual(first['mean'], '90.00')
        self.assertIsNone(prices[self.products[1]['ean']]['reference'])
        stale = summary(self.products, self.database.observations(), self.config, now=NOW + timedelta(days=8))
        self.assertIsNone(stale[self.products[0]['ean']]['reference'])
        external = [{**self.products[1], 'price': '77', 'date': '2026-10-14', 'source': 'FICHIER FICTIF'}]
        fallback = summary(self.products, [], self.config, external, now=NOW)
        second = fallback[self.products[1]['ean']]
        self.assertEqual((second['reference'], second['count'], second['quality']), ('77.00', 0, 'Repli externe'))
        self.assertIsNone(summary(self.products, [], self.config, external * 2, now=NOW)[self.products[1]['ean']]['reference'])
        by_ref = [{**external[0], 'ean': ''}]
        self.assertEqual(summary(self.products, [], self.config, by_ref, now=NOW)[self.products[1]['ean']]['reference'], '77.00')
        uncertain = [{**external[0], 'ean': '', 'ref': ''}]
        self.assertIsNone(summary(self.products, [], self.config, uncertain, now=NOW)[self.products[1]['ean']]['reference'])
        promoted = quote(self.products[1], '50', promotion=True, promotion_conditions='Offre publique fictive')
        self.ingest(records=[promoted])
        self.assertIsNone(summary(self.products, self.database.observations(), self.config, now=NOW)[self.products[1]['ean']]['reference'])
        self.assertEqual(summary(self.products, self.database.observations(), {**self.config, 'include_promotions': True}, now=NOW)[self.products[1]['ean']]['reference'], '50.00')

    def test_simulations_and_changed_product_identity_are_excluded_in_production(self):
        self.ingest(simulated=True)
        observations = self.database.observations()
        self.assertIsNone(summary(self.products, observations, self.config, now=NOW)[self.products[0]['ean']]['reference'])
        self.assertEqual(summary(self.products, observations, self.config, now=NOW, allow_simulated=True)[self.products[0]['ean']]['reference'], '60.00')
        changed = [{**self.products[0], 'profile': 'AUTRE PRODUIT'}, self.products[1]]
        self.assertIsNone(summary(changed, observations, self.config, now=NOW, allow_simulated=True)[self.products[0]['ean']]['reference'])

    def test_collecting_does_not_publish_or_change_frozen_prices(self):
        state = empty_state()
        state['products'] = self.products
        state['radar'] = self.config
        self.ingest(records=[quote(self.products[0]), quote(self.products[1], '65')])
        prices = summary(self.products, self.database.observations(), self.config, now=NOW)
        state = mutate(state, 'version', 'pricing', radar_prices=prices)
        state = mutate(state, 'validate', 'pricing', id='V1')
        state = mutate(state, 'publish', 'pricing', id='V1')
        frozen = deepcopy(state['versions'])
        self.ingest(records=[quote(self.products[0], '65', observed_at=(NOW + timedelta(days=1)).isoformat())], now=NOW + timedelta(days=1))
        self.assertEqual(state['versions'], frozen)
        self.assertEqual(state['versions'][0]['status'], 'Publiée')
        self.assertEqual(state['versions'][0]['rows'][0]['recommended'], '60.00')

    def test_analysis_excel_csv_preserve_ean_and_numeric_prices(self):
        self.ingest()
        prices = summary(self.products, self.database.observations(), self.config, now=NOW)
        state = empty_state(); state['products'] = self.products
        rows = calculate(state, radar_prices=prices)
        frame = comparison_frame(self.products, prices, rows)
        book = load_workbook(BytesIO(excel_bytes(frame)))
        self.assertEqual(book.active['A2'].value, self.products[0]['ean'])
        self.assertIsInstance(book.active['E2'].value, (int, float))
        parsed = pd.read_csv(BytesIO(csv_bytes(frame)), sep=';', dtype={'EAN': str})
        self.assertEqual(parsed.iloc[0]['EAN'], self.products[0]['ean'])
        self.assertTrue(pd.isna(parsed.iloc[1]['Norauto HT']))
        compact = pricing_export_frame(rows, [])
        self.assertEqual(compact.columns.tolist(), ['Marque', 'Saison', 'Code EAN', 'Prix HT', 'Remise BF (%)'])
        self.assertEqual(compact.iloc[0]['Remise BF (%)'], 40)


class FeedAndHistoryTests(unittest.TestCase):
    def test_feed_authorization_is_checked_before_any_network_call(self):
        session = MagicMock()
        connector = AuthorizedFeedConnector('Norauto', {'approved': False}, session)
        with self.assertRaises(PermissionError):
            connector.fetch(demo_catalog(1), settings({}))
        session.get.assert_not_called()

    def test_authorized_bulk_feed_mock_and_no_redirect_or_retries(self):
        response = MagicMock()
        response.status_code = 200
        response.__enter__.return_value = response
        response.iter_content.return_value = [json.dumps([quote(demo_catalog(1)[0])]).encode()]
        session = MagicMock(); session.get.return_value = response
        config = {'approved': True, 'authorization_reference': 'CONTRAT FICTIF DE TEST', 'approved_by': 'TEST',
                  'approved_until': '2099-01-01T00:00:00Z', 'url': 'https://feed.example.invalid/observations',
                  'allowed_hosts': ['feed.example.invalid'], 'token': 'SECRET FICTIF'}
        with patch('eurotyre.radar.connectors.public_https') as check:
            check.return_value.hostname = 'feed.example.invalid'
            connector = AuthorizedFeedConnector('Norauto', config, session)
            rows = connector.fetch(demo_catalog(1), settings({}))
            self.assertEqual(len(rows), 1)
            self.assertNotIn('token', rows[0])
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            response.status_code = 403
            with self.assertRaises(PermissionError):
                connector.fetch(demo_catalog(1), settings({}))
            self.assertEqual(session.get.call_count, 2)  # Une seule requête par tentative.

    def test_history_never_invents_missing_90_day_or_previous_values(self):
        def item(days, price):
            return {'status': 'valid', 'observed_at': (NOW - timedelta(days=days)).isoformat(), 'price_ht': price}
        metrics = history_metrics([item(30, '50'), item(7, '60'), item(1, '60'), item(0, '66')], NOW)
        self.assertEqual(metrics['previous'], '60.00')
        self.assertEqual(metrics['last_variation'], '10.00')
        self.assertEqual(metrics['variation_7'], '10.00')
        self.assertEqual(metrics['variation_30'], '32.00')
        self.assertIsNone(metrics['variation_90'])
        self.assertEqual(metrics['changes'], 2)
        self.assertIsNone(history_metrics([item(0, '60')], NOW)['previous'])
        self.assertTrue(all(value is None for value in history_metrics([], NOW).values()))

    def test_settings_permissions_selection_and_no_production_demo_catalog(self):
        state = empty_state(); state['products'] = demo_catalog(1)
        with self.assertRaises(PermissionError):
            mutate(state, 'radar_settings', 'viewer', config=configuration(state['products']))
        with self.assertRaises(ValueError):
            mutate(state, 'radar_demo', 'admin', demo_mode=False)
        state = mutate(state, 'radar_settings', 'pricing', config=configuration(state['products']))
        self.assertEqual(len(state['radar']['selected_eans']), 1)
        self.assertEqual(empty_state()['products'], [])


if __name__ == '__main__':
    unittest.main()
