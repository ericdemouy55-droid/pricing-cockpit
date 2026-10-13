import unittest
from pathlib import Path
APP = str(Path(__file__).resolve().parents[1]/'eurotyre_app.py')
from streamlit.testing.v1 import AppTest
from eurotyre.engine import calculate

class AppTests(unittest.TestCase):
    def test_overview_comparisons_and_removed_cost_controls(self):
        app = AppTest.from_file(APP,default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, 'Outil prix Eurotyre')
        self.assertEqual(len(app.metric), 4)
        self.assertEqual([metric.label for metric in app.metric], ['Été', 'Hiver', 'Toutes saisons', 'Total'])
        self.assertEqual([metric.value for metric in app.metric], ['+0.41 %', '+0.55 %', '+0.36 %', '+0.44 %'])
        seasons = app.dataframe[0].value
        self.assertEqual(len(seasons), 18)
        self.assertNotIn('Réf. comparées', seasons.columns)
        self.assertTrue(seasons.loc[seasons.Marque.eq('Michelin'), 'Écart Eurotyre / marché (%)'].eq(3).all())
        self.assertIn('Écart des prix vs marché', [heading.value for heading in app.subheader])
        self.assertTrue(seasons['Marché / BF (%)'].eq(37.5).all())
        brands = app.dataframe[1].value
        self.assertEqual(len(brands), 6)
        self.assertNotIn('Réf. comparées', brands.columns)
        self.assertEqual(brands.loc[brands.Marque.eq('Michelin'), 'Écart moyen (%)'].iloc[0], 3)
        app.selectbox[0].set_value('Michelin').run()
        self.assertEqual(app.dataframe[0].value.Marque.tolist(), ['Michelin'] * 3)
        app.selectbox[1].set_value('Hiver').run()
        self.assertEqual(app.dataframe[0].value[['Marque', 'Saison']].values.tolist(), [['Michelin', 'Hiver']])
        self.assertEqual([metric.value for metric in app.metric], ['+0.41 %', '+0.55 %', '+0.36 %', '+0.44 %'])
        app.selectbox[0].set_value('Toutes les marques').run()
        app.selectbox[1].set_value('Toutes les saisons').run()
        self.assertEqual(len(app.dataframe[0].value), 18)
        for page in ('Règles tarifaires','Catalogue','Export'):
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
        self.assertNotIn('Simulation', app.sidebar.radio[0].options)
        for tab in ('Imports & rapprochement','Règles tarifaires','Catalogue','Export','Versions & diffusion','Guide & historique','Vue d’ensemble'):
            app.sidebar.radio[0].set_value(tab).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_export_uses_saved_bf_prices_and_exact_columns(self):
        app = AppTest.from_file(APP, default_timeout=30).run()
        app.sidebar.radio[0].set_value('Règles tarifaires').run()
        app.selectbox(key='rules_brand').set_value('Michelin').run()
        app.selectbox(key='rules_season').set_value('Été').run()
        next(n for n in app.number_input if n.label == 'Remise BF Michelin Été 16"').set_value(40).run()
        next(b for b in app.button if b.label == 'Enregistrer les remises BF').click().run()
        app.sidebar.radio[0].set_value('Export').run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        frame = app.dataframe[0].value
        self.assertEqual(frame.columns.tolist(), ['Marque', 'Saison', 'Code EAN', 'Prix HT', 'Remise BF (%)'])
        self.assertEqual(len(frame), 66)
        row = frame.loc[frame['Code EAN'].eq('2000000000036')].iloc[0]
        self.assertEqual(row['Prix HT'], 70.08)
        self.assertEqual(row['Remise BF (%)'], 40)
        self.assertTrue(any('6 références sans prix calculé' in message.value for message in app.info))

    def test_bf_grid_filters_draft_save_and_clear(self):
        app = AppTest.from_file(APP, default_timeout=30).run()
        app.sidebar.radio[0].set_value('Règles tarifaires').run()
        app.selectbox(key='rules_brand').set_value('Michelin').run()
        app.selectbox(key='rules_season').set_value('Été').run()
        self.assertEqual(len(app.number_input), 7)  # Six remises et le seuil de contrôle.
        label = 'Remise BF Michelin Été 16"'
        next(n for n in app.number_input if n.label == label).set_value(40).run()
        app.selectbox(key='rules_season').set_value('Hiver').run()
        app.selectbox(key='rules_season').set_value('Été').run()
        self.assertEqual(next(n for n in app.number_input if n.label == label).value, 40)
        # Les références de marché restent des textes, sans champ de saisie.
        self.assertTrue(any(c.value == '37,50 %' for c in app.caption))
        self.assertFalse(any('Marché' in n.label for n in app.number_input))
        next(b for b in app.button if b.label == 'Enregistrer les remises BF').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(calculate(app.session_state.pricing_state)[36]['recommended'], '70.08')
        self.assertFalse(app.session_state['bf_grid_draft'])
        self.assertEqual(next(n for n in app.number_input if n.label == label).value, 40)
        next(n for n in app.number_input if n.label == label).set_value(None).run()
        next(b for b in app.button if b.label == 'Enregistrer les remises BF').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(calculate(app.session_state.pricing_state)[36]['recommended'], '75.19')

    def test_bf_grid_saves_edits_hidden_by_filters(self):
        app = AppTest.from_file(APP, default_timeout=30).run()
        app.sidebar.radio[0].set_value('Règles tarifaires').run()
        app.selectbox(key='rules_brand').set_value('Michelin').run()
        app.selectbox(key='rules_season').set_value('Été').run()
        next(n for n in app.number_input if n.label == 'Remise BF Michelin Été 16"').set_value(40).run()
        app.selectbox(key='rules_season').set_value('Hiver').run()
        next(n for n in app.number_input if n.label == 'Remise BF Michelin Hiver 17"').set_value(35).run()
        next(b for b in app.button if b.label == 'Enregistrer les remises BF').click().run()
        self.assertFalse(app.exception)
        rules = [r for r in app.session_state.pricing_state['rules'] if r.get('base') == 'bf']
        self.assertEqual({(r['season'], r['min'], r['discount']) for r in rules},
                         {('Été', 16, '40.00'), ('Hiver', 17, '35.00')})

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

