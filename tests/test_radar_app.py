"""Parcours UI sur des observations exclusivement simulées."""
import unittest
from copy import deepcopy
from pathlib import Path
from streamlit.testing.v1 import AppTest
from eurotyre.radar.ui import current
from eurotyre.radar.storage import SQLiteRadarStore

APP = str(Path(__file__).resolve().parents[1] / 'eurotyre_app.py')


class RadarAppTests(unittest.TestCase):
    def test_full_demo_pilot_history_working_prices_and_immutable_published_version(self):
        app = AppTest.from_file(APP, default_timeout=60).run()
        app.sidebar.radio[0].set_value('Market Price Radar').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.metric[0].value, '0 / 200')
        app.button(key='radar_demo_catalog').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.metric[0].value, '200 / 200')
        self.assertEqual(app.metric[1].value, '0')
        app.button(key='radar_demo_history').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.metric[1].value, '200')
        self.assertEqual(app.metric[3].value, '4')
        self.assertTrue(any('SIMULATION' in w.value for w in app.warning))
        comparison = app.dataframe[0].value
        self.assertEqual(len(comparison), 200)
        self.assertTrue(comparison['Écart Eurotyre / marché %'].eq('+0.00 %').all())
        self.assertEqual(comparison.iloc[0]['Prix marché HT'], '61.50 €')
        app.sidebar.radio[0].set_value('Export').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(len(app.dataframe[0].value), 200)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Prix HT'], 61.5)
        self.assertEqual(app.dataframe[0].value.iloc[0]['Remise BF (%)'], 38.5)
        app.sidebar.radio[0].set_value('Versions & diffusion').run()
        app.button[0].click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        app.button[1].click().run()
        self.assertEqual(app.session_state.pricing_state['versions'][0]['status'], 'Validée')
        next(b for b in app.button if b.label == 'Publier en interne').click().run()
        frozen = deepcopy(app.session_state.pricing_state['versions'])
        app.sidebar.radio[0].set_value('Market Price Radar').run()
        app.button(key='radar_demo_history').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state.pricing_state['versions'], frozen)
        database = SQLiteRadarStore(app.session_state.radar_demo_database)
        self.assertEqual(len(database.observations()), 6400)
        prices, _ = current(app.session_state.pricing_state, database, 'eurotyre', 'production')
        self.assertTrue(all(p['reference'] is None for p in prices.values()))
        app.sidebar.radio[0].set_value('Vue d’ensemble').run()
        self.assertEqual(len(app.metric), 4)
        self.assertEqual([m.value for m in app.metric], ['+0.00 %'] * 4)

    def test_unconfigured_sources_create_a_report_without_appearing_operational(self):
        app = AppTest.from_file(APP, default_timeout=60).run()
        app.sidebar.radio[0].set_value('Market Price Radar').run()
        app.button(key='radar_demo_catalog').click().run()
        app.button(key='radar_collect').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.metric[1].value, '0')
        self.assertEqual(app.metric[4].value, 'Non disponible')
        database = SQLiteRadarStore(app.session_state.radar_demo_database)
        self.assertEqual([r['status'] for r in database.runs()[0]['connectors']], ['disabled'] * 4)
        self.assertEqual(database.observations(), [])


if __name__ == '__main__':
    unittest.main()
