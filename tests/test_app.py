import unittest
from pathlib import Path
APP = str(Path(__file__).resolve().parents[1]/'eurotyre_app.py')
from streamlit.testing.v1 import AppTest

class AppTests(unittest.TestCase):
    def test_overview_comparisons_and_removed_cost_controls(self):
        app = AppTest.from_file(APP,default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, 'Outil prix Eurotyre')
        seasons = app.dataframe[0].value
        self.assertEqual(len(seasons), 18)
        self.assertEqual(seasons['Réf. comparées'].sum(), 66)
        self.assertTrue(seasons['Marché / BF (%)'].eq(37.5).all())
        brands = app.dataframe[1].value
        self.assertEqual(len(brands), 6)
        self.assertEqual(brands.loc[brands.Marque.eq('Michelin'), 'Écart moyen (%)'].iloc[0], 3)
        for page in ('Règles tarifaires','Simulation','Catalogue'):
            app.sidebar.radio[0].set_value(page).run()
            self.assertFalse(app.exception)
            for frame in app.dataframe:
                text = ' '.join(frame.value.columns).lower()
                self.assertNotIn('marge', text)
                self.assertNotIn('taux de marque', text)
                self.assertNotIn('pa net', text)
            self.assertFalse(any('Taux de marque' in number.label for number in app.number_input))

    def test_all_pages_render(self):
        app = AppTest.from_file(APP,default_timeout=30).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        for tab in ('Imports & rapprochement','Règles tarifaires','Simulation','Catalogue','Versions & diffusion','Guide & historique','Vue d’ensemble'):
            app.sidebar.radio[0].set_value(tab).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_version_and_validation_block(self):
        app = AppTest.from_file(APP,default_timeout=30).run()
        app.sidebar.radio[0].set_value('Versions & diffusion').run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state.pricing_state['versions']),1)
        app.button[1].click().run()
        self.assertTrue(any('Validation bloquée' in e.value for e in app.error))
        self.assertEqual(app.session_state.pricing_state['versions'][0]['status'],'Brouillon')

    def test_production_fails_closed_without_config(self):
        app = AppTest.from_file(APP,default_timeout=30)
        app.secrets['app'] = {'mode':'production'}
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Accès fermé' in e.value for e in app.error))
        self.assertFalse(app.dataframe)

if __name__ == '__main__': unittest.main()

