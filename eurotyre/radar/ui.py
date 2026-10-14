"""Interface Radar ajoutée à la navigation Streamlit existante."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import pandas as pd
import streamlit as st
from ..engine import cash, decimal, SEASONS
from ..exports import excel_bytes, csv_bytes
from ..imports import read_upload
from . import settings, RETAILERS
from .catalog import eligible_catalog, select_pilot, fingerprint
from .connectors import configured_connectors, FileConnector
from .market import summary, comparison_frame, history_metrics
from .pipeline import collect
from .storage import SQLiteRadarStore, PostgresRadarStore

HEADERS = ['ean', 'ref', 'brand', 'profile', 'dimension', 'load', 'speed', 'season',
           'xl', 'runflat', 'homologation', 'url', 'price', 'price_type', 'currency',
           'tax_rate', 'nature', 'mounting_included', 'delivery_included', 'member_only',
           'conditional_price', 'promotion', 'promotion_conditions', 'usual_price',
           'observed_at', 'zone', 'center', 'availability', 'mounting_fee', 'delivery_fee']


def backend(pricing_store):
    if pricing_store:
        return PostgresRadarStore(pricing_store.url)
    if 'radar_demo_database' not in st.session_state:
        fd, path = tempfile.mkstemp(prefix='eurotyre-radar-demo-', suffix='.sqlite')
        os.close(fd)
        st.session_state.radar_demo_database = path
    return SQLiteRadarStore(st.session_state.radar_demo_database)


def pilot(state):
    eligible, _ = eligible_catalog(state['products'])
    selected = set(settings(state)['selected_eans'])
    return [p for p in eligible if p['ean'] in selected]


def current(state, database, workspace, mode):
    config = settings(state)
    since = (datetime.now(timezone.utc) - timedelta(days=config['freshness_days'])).isoformat()
    observations = database.observations(workspace, since=since)
    prices = summary(pilot(state), observations, config, state['market'], allow_simulated=mode == 'demo')
    return prices, observations


def analysis_export(state, prices, rows):
    return comparison_frame(pilot(state), prices, rows)


def simulated_history(products, config, database, workspace):
    now = datetime.now(timezone.utc)
    reports = []
    for days in (30, 7, 1, 0):
        date = now - timedelta(days=days)
        connectors = []
        for j, retailer in enumerate(RETAILERS):
            records = []
            for i, product in enumerate(products):
                records.append({**{k: product.get(k) for k in ('ean', 'ref', 'brand', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat', 'homologation')},
                    'url': f'https://simulation.invalid/{j}/{product["ean"]}',
                    'price': cash(decimal(product['bf']) * (Decimal('.60') + Decimal(j) / 100 + Decimal(days % 4) / 100)),
                    'price_type': 'HT', 'currency': 'EUR', 'tax_rate': '20', 'nature': 'pneu_seul',
                    'mounting_included': False, 'delivery_included': False, 'member_only': False,
                    'conditional_price': False, 'promotion': False, 'promotion_conditions': '',
                    'observed_at': date.isoformat(), 'zone': config['zone'],
                    'center': config['centers'][retailer], 'availability': 'SIMULATION',
                })
            connectors.append(FileConnector(retailer, records, 'JEU FICTIF DE TEST', simulated=True))
        reports.append(collect(products, connectors, database, config, workspace, now=date))
    return reports


def display_frame(frame):
    result = frame.copy()
    for col in [name + ' HT' for name in RETAILERS] + ['Prix marché HT', 'Prix Eurotyre HT']:
        result[col] = result[col].map(lambda v: 'Non disponible' if pd.isna(v) else f'{v:.2f} €')
    result['Écart Eurotyre / marché %'] = result['Écart Eurotyre / marché %'].map(lambda v: 'Non disponible' if pd.isna(v) else f'{v:+.2f} %')
    return result.fillna('Non disponible')


def render(state, rows, database, prices, observations, cfg, mode, workspace, can, execute, user, error=None):
    config = settings(state)
    products = pilot(state)
    if error:
        st.error('Historique indisponible. Configure la base et applique la migration Radar avant toute collecte réelle.')
    if not config['enabled']:
        st.info('Le Radar est désactivé pour les calculs de travail. Active son alimentation dans les paramètres après contrôle des données.')
    if len(products) < 200:
        st.info(f'{len(products)} références sélectionnées sur un objectif de 200. Aucun pneu manquant n’est inventé.')
    runs = [] if error else database.runs(workspace)
    data_runs = [r for r in runs if any(c['status'] == 'completed' and c['observations'] for c in r['connectors'])]
    covered = sum(s['count'] > 0 for s in prices.values())
    names = {name for s in prices.values() for name, item in s['retailers'].items() if item}
    metrics = st.columns(6)
    metrics[0].metric('Références suivies', f'{len(products)} / 200')
    metrics[1].metric('Avec prix concurrent valide', covered)
    metrics[2].metric('Couverture du marché', f'{covered / len(products) * 100:.1f} %' if products else 'Non disponible')
    metrics[3].metric('Concurrents avec prix valide', len(names))
    metrics[4].metric('Dernière collecte', data_runs[0]['started_at'][:16].replace('T', ' ') if data_runs else 'Non disponible')
    metrics[5].metric('Anomalies récentes', sum(o.get('status') in ('pending', 'rejected') for o in observations))
    st.caption(f'Zone : {config["zone"]} · {config["freshness_days"]} jours de fraîcheur · {config["method"]} · Prix du pneu seul en EUR HT. Dates conservées en UTC.')
    if any(o.get('simulated') for o in observations):
        st.warning('SIMULATION — les observations fictives ne représentent aucun prix réellement pratiqué par les enseignes.')
    comparison, history, selection, sources, validation = st.tabs(['Comparaison', 'Historique', 'Catalogue & paramètres', 'Collecte & sources', 'Anomalies & rapports'])
    with comparison:
        a, b, c, d = st.columns(4)
        brands = a.multiselect('Marques', sorted({p['brand'] for p in products}), key='radar_brands')
        manufacturers = b.multiselect('Manufacturiers', sorted({p['manufacturer'] for p in products}), key='radar_manufacturers')
        seasons = c.multiselect('Saisons', list(SEASONS), key='radar_seasons')
        diameters = d.multiselect('Diamètres', sorted({p['diameter'] for p in products}), key='radar_diameters')
        a, b, c = st.columns(3)
        retailers = a.multiselect('Enseignes avec un prix valide', list(RETAILERS), key='radar_retailers')
        availability = b.selectbox('Disponibilité du prix', ['Toutes', 'Prix concurrent valide', 'Repli externe', 'Non disponible'], key='radar_availability')
        match_status = c.selectbox('Statut de rapprochement', ['Tous', 'Validé', 'À valider', 'Rejeté'], key='radar_match_status')
        status_eans = {o.get('ean') for o in observations if o.get('status') == {'À valider': 'pending', 'Rejeté': 'rejected'}.get(match_status)}
        selected = [p for p in products if (not brands or p['brand'] in brands) and
                    (not manufacturers or p['manufacturer'] in manufacturers) and (not seasons or p['season'] in seasons) and
                    (not diameters or p['diameter'] in diameters) and
                    (not retailers or any(prices[p['ean']]['retailers'][name] for name in retailers)) and
                    (availability == 'Toutes' or availability == 'Prix concurrent valide' and prices[p['ean']]['count'] > 0 or
                     availability == 'Repli externe' and prices[p['ean']]['quality'] == 'Repli externe' or
                     availability == 'Non disponible' and prices[p['ean']]['reference'] is None) and
                    (match_status == 'Tous' or match_status == 'Validé' and prices[p['ean']]['count'] > 0 or p['ean'] in status_eans)]
        frame = comparison_frame(selected, prices, rows)
        st.dataframe(display_frame(frame), hide_index=True, width='stretch', height=460)
        st.caption(f'{len(selected)} références affichées. Couverture = références avec au moins un prix concurrent valide / références suivies. Le repli externe est exclu de la couverture concurrentielle.')
        with st.expander('Statistiques de la référence marché'):
            st.dataframe(pd.DataFrame([{'EAN': p['ean'], 'Minimum HT': prices[p['ean']]['min'],
                'Maximum HT': prices[p['ean']]['max'], 'Moyenne HT': prices[p['ean']]['mean'],
                'Médiane HT': prices[p['ean']]['median'], 'Enseignes': prices[p['ean']]['count'],
                'Date': prices[p['ean']]['last']} for p in selected]).fillna('Non disponible'), hide_index=True, width='stretch')
        st.caption('Export d’analyse du scénario de travail ; la diffusion du tarif reste dans Versions & diffusion.')
        a, b = st.columns(2)
        a.download_button('Analyse concurrentielle Excel', excel_bytes(frame), file_name='Eurotyre_Radar_analyse.xlsx', key='radar_analysis_xlsx', disabled=frame.empty)
        b.download_button('Analyse concurrentielle CSV', csv_bytes(frame), file_name='Eurotyre_Radar_analyse.csv', key='radar_analysis_csv', disabled=frame.empty)
    with history:
        if not products:
            st.info('Sélectionne des références dans Catalogue & paramètres pour consulter leur historique.')
        else:
            by_ean = {p['ean']: p for p in products}
            ean = st.selectbox('Fiche pneumatique', list(by_ean), format_func=lambda e: f'{e} · {by_ean[e]["brand"]} · {by_ean[e]["dimension"]} · {by_ean[e]["profile"] if by_ean[e].get("profile") else "Profil non renseigné"}', key='radar_history_ean')
            period = st.radio('Période', ['7 jours', '30 jours', '90 jours', 'Historique complet'], horizontal=True, key='radar_history_period')
            details = [] if error else database.observations(workspace, ean=ean)
            now = datetime.now(timezone.utc)
            valid = [o for o in details if o.get('status') == 'valid' and o.get('product_fingerprint') == fingerprint(by_ean[ean]) and
                     (mode == 'demo' or not o.get('simulated')) and o.get('zone') == config['zone'] and
                     config['centers'].get(o['retailer']) and o.get('center') == config['centers'][o['retailer']]]
            if valid:
                import plotly.graph_objects as go
                first = min(pd.Timestamp(o['observed_at']) for o in valid) if period == 'Historique complet' else pd.Timestamp(now - timedelta(days=int(period.split()[0]) - 1))
                days = pd.date_range(first.tz_convert('Europe/Paris').normalize(), pd.Timestamp(now).tz_convert('Europe/Paris').normalize(), freq='D')
                figure = go.Figure()
                colors = ['#005fa8', '#e00030', '#27843a', '#543a90']
                for retailer, color in zip(RETAILERS, colors):
                    items = [o for o in valid if o['retailer'] == retailer]
                    daily = {pd.Timestamp(o['observed_at']).tz_convert('Europe/Paris').normalize(): o for o in items}
                    figure.add_trace(go.Scatter(x=list(days), y=[float(daily[d]['price_ht']) if d in daily else None for d in days],
                        name=retailer, mode='lines+markers', connectgaps=False, line={'color': color},
                        customdata=[daily[d]['observed_at'] if d in daily else '' for d in days],
                        hovertemplate='%{y:.2f} € HT<br>%{customdata}<extra>%{fullData.name}</extra>'))
                    promos = [d for d in days if d in daily and daily[d].get('promotion')]
                    if promos:
                        figure.add_trace(go.Scatter(x=promos, y=[float(daily[d]['price_ht']) for d in promos], name=f'{retailer} · promotion',
                            mode='markers', marker={'symbol': 'diamond', 'size': 12, 'color': color}))
                figure.update_layout(yaxis_title='Prix observé EUR HT', xaxis_title='Date du relevé (Europe/Paris)', height=380, margin={'t': 20})
                st.plotly_chart(figure, width='stretch', key='radar_history_chart')
                st.caption('Les jours sans relevé restent vides. Ils ne prouvent aucune stabilité de prix. Les points promotionnels sont visibles même lorsque les promotions sont exclues de la référence marché.')
                metrics_rows = []
                for retailer in RETAILERS:
                    m = history_metrics([o for o in valid if o['retailer'] == retailer])
                    metrics_rows.append({'Enseigne': retailer, 'Actuel HT': m['current'], 'Précédent HT': m['previous'],
                        'Dernière variation %': m['last_variation'], '7 jours %': m['variation_7'], '30 jours %': m['variation_30'],
                        '90 jours %': m['variation_90'], 'Minimum HT': m['min'], 'Maximum HT': m['max'], 'Changements observés': m['changes']})
                st.dataframe(pd.DataFrame(metrics_rows).fillna('Non disponible'), hide_index=True, width='stretch')
                st.caption('Variations à 7/30/90 jours : par rapport au dernier relevé, avec un point de référence antérieur de 7 jours maximum. Les métriques portent sur tout l’historique validé ; « actuel » signifie dernier prix observé, qui peut être ancien.')
            else:
                st.info('Aucun relevé validé pour ce pneumatique et les centres sélectionnés.')
            st.dataframe(pd.DataFrame([{'Date': o.get('observed_at'), 'Enseigne': o['retailer'], 'Centre': o.get('center'),
                'Prix original': o.get('price_original'), 'Type': o.get('price_type'), 'TVA %': o.get('tax_rate'), 'HT': o.get('price_ht'),
                'Promotion': o.get('promotion'), 'Statut': o.get('status'), 'Source': o.get('url'), 'Contrôles': ' · '.join(o.get('reasons', []))} for o in details]).fillna('Non disponible'), hide_index=True, width='stretch')
    with selection:
        eligible, issues = eligible_catalog(state['products'])
        st.caption(f'{len(eligible)} références BF avec un EAN unique et une clé de contrôle valide. La sélection automatique équilibre marque, saison, diamètre et type de véhicule disponibles ; elle ne remplace pas une pondération par les ventes.')
        if st.button('Sélectionner automatiquement jusqu’à 200 références', disabled=not can('radar_settings') or not eligible, key='radar_auto_select'):
            execute('radar_settings', config={**config, 'selected_eans': [p['ean'] for p in select_pilot(state['products'])]})
        available = {p['ean']: p for p in eligible}
        with st.form('radar_parameters'):
            chosen = st.multiselect('Sélection manuelle des EAN', list(available), default=[e for e in config['selected_eans'] if e in available], max_selections=200,
                format_func=lambda e: f'{e} · {available[e]["brand"]} · {available[e]["dimension"]} · {available[e]["season"]}')
            zone = st.text_input('Zone de référence', value=config['zone'])
            centers = {}
            st.caption('Indique l’identifiant du centre tel qu’il apparaît dans la source. Utilise « National » uniquement si la source confirme un tarif national. Un centre non sélectionné ne contribue pas au marché.')
            for column, name in zip(st.columns(4), RETAILERS):
                centers[name] = column.text_input('Centre ' + name, value=config['centers'][name])
            method = st.selectbox('Méthode de référence', ['median', 'mean', 'min', 'max'], index=['median', 'mean', 'min', 'max'].index(config['method']),
                format_func=lambda k: {'median': 'Médiane', 'mean': 'Moyenne', 'min': 'Minimum', 'max': 'Maximum'}[k])
            freshness = st.number_input('Fraîcheur maximale (jours)', min_value=1, max_value=90, value=int(config['freshness_days']))
            change = st.number_input('Variation inhabituelle à contrôler (%)', min_value=1., max_value=100., value=float(config['max_price_change']))
            promos = st.checkbox('Inclure les promotions publiques sans condition particulière dans le marché', value=config['include_promotions'])
            enabled = st.checkbox('Alimenter les calculs de travail du Pricing Manager avec le Radar', value=config['enabled'])
            if st.form_submit_button('Enregistrer les paramètres Radar', disabled=not can('radar_settings')):
                execute('radar_settings', config={'selected_eans': chosen, 'zone': zone, 'centers': centers, 'method': method,
                    'freshness_days': freshness, 'max_price_change': change, 'include_promotions': promos, 'enabled': enabled})
        if issues:
            with st.expander(f'{len(issues)} lignes BF exclues du pilote'):
                st.dataframe(pd.DataFrame([{'EAN': i['ean'], 'Marque': i['brand'], 'Contrôles': ' · '.join(i['reasons'])} for i in issues]), hide_index=True, width='stretch')
        if products:
            st.dataframe(pd.DataFrame([{k: p.get(k) for k in ('manufacturer', 'brand', 'ean', 'ref', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat', 'homologation', 'vehicle', 'bf')} for p in products]), hide_index=True, width='stretch')
    with sources:
        source_configs = cfg.get('radar_sources', {})
        last_by_name = {c['retailer']: c for r in reversed(runs) for c in r['connectors']}
        st.dataframe(pd.DataFrame([{'Enseigne': name, 'Flux automatique': 'À tester' if source_configs.get(name) else 'Non configuré',
            'Dernier état': last_by_name.get(name, {}).get('status', 'Non disponible'),
            'Dernier rapport': last_by_name.get(name, {}).get('message', 'Voir les observations et leur provenance')} for name in RETAILERS]), hide_index=True, width='stretch')
        st.caption('Aucune extraction des sites marchands n’est activée. Les quatre connecteurs acceptent des fichiers de provenance autorisée ou un flux JSON/CSV autorisé configuré séparément.')
        if st.button('Lancer la collecte des flux autorisés', disabled=not can('radar_collect') or error is not None or not products, key='radar_collect'):
            try:
                report = collect(products, configured_connectors(source_configs), database, config, workspace)
                completed = sum(c['status'] == 'completed' for c in report['connectors'])
                st.session_state.notice = f'Exécution terminée : {completed} source(s) traitée(s), rapport enregistré.'
                st.rerun()
            except Exception:
                st.error('Enregistrement impossible ; aucune collecte ne peut être confirmée.')
        st.markdown('**Importer un relevé autorisé**')
        model = pd.DataFrame(columns=HEADERS)
        a, b = st.columns(2)
        a.download_button('Modèle de relevé Excel', excel_bytes(model), file_name='Radar_modele.xlsx', key='radar_template_xlsx')
        b.download_button('Modèle de relevé CSV', csv_bytes(model), file_name='Radar_modele.csv', key='radar_template_csv')
        retailer = st.selectbox('Enseigne du fichier', list(RETAILERS), key='radar_import_retailer')
        upload = st.file_uploader('Relevés concurrentiels XLSX ou CSV', type=['csv', 'xlsx'], key='radar_upload', disabled=not can('radar_collect') or bool(error))
        authorization = st.text_input('Référence de provenance / autorisation', placeholder='Contrat de flux, fichier partenaire autorisé…', key='radar_authorization')
        confirmed = st.checkbox('Je confirme que la source autorise cet usage des prix', key='radar_authorized_file')
        fictional = st.checkbox('Ce fichier contient uniquement des données fictives', key='radar_fictional_file') if mode == 'demo' else False
        if upload:
            try:
                frame, sheets = read_upload(upload.getvalue(), upload.name)
                if sheets:
                    sheet = st.selectbox('Feuille de relevés', sheets, key='radar_import_sheet')
                    frame, _ = read_upload(upload.getvalue(), upload.name, sheet)
                if not {'price', 'observed_at', 'url', 'zone', 'center'}.issubset(frame.columns):
                    st.error('Utilise les en-têtes du modèle : price, observed_at, url, zone et center sont obligatoires.')
                else:
                    st.dataframe(frame.head(10), hide_index=True, width='stretch')
                    if st.button('Contrôler et enregistrer ces observations', disabled=not products or not confirmed or not authorization or (mode == 'demo' and not fictional) or not can('radar_collect'), key='radar_ingest'):
                        report = collect(products, [FileConnector(retailer, frame.to_dict('records'), authorization, simulated=mode == 'demo')], database, config, workspace)
                        st.session_state.notice = f'Relevé enregistré : {report["connectors"][0]["valid"]} valide(s). Les anomalies restent hors calcul.'
                        st.rerun()
            except Exception:
                st.error('Lecture ou enregistrement du fichier impossible. Aucun import réussi ne peut être confirmé.')
        if mode == 'demo':
            st.markdown('**Essai avec données fictives**')
            st.caption('Le pilote fictif remplace le catalogue de cette session de démonstration. Les règles tarifaires et les versions déjà créées sont conservées.')
            if st.button('Charger un pilote fictif de 200 références', disabled=not can('radar_demo'), key='radar_demo_catalog'):
                execute('radar_demo', demo_mode=True)
            if st.button('Charger un historique simulé (4 dates)', disabled=not can('radar_collect') or not products or bool(error) or any(not e for e in config['centers'].values()), key='radar_demo_history'):
                simulated_history(products, config, database, workspace)
                st.session_state.notice = 'Historique simulé ajouté à J−30, J−7, J−1 et J. Aucune enseigne réelle n’a été interrogée.'
                st.rerun()
        audit_path = Path(__file__).resolve().parents[2] / 'docs' / 'RADAR_FAISABILITE.md'
        if audit_path.exists():
            st.download_button('Rapport de faisabilité des quatre sources', audit_path.read_bytes(), file_name=audit_path.name, key='radar_feasibility')
    with validation:
        pending = [o for o in observations if o.get('status') in ('pending', 'rejected')]
        st.dataframe(pd.DataFrame([{'ID': o['id'], 'EAN': o.get('ean'), 'Enseigne': o['retailer'],
            'Date': o.get('observed_at'), 'Statut': o.get('status'), 'Qualité / 100': o.get('quality'),
            'Contrôles': ' · '.join(o.get('reasons', []))} for o in pending]).fillna('Non disponible'), hide_index=True, width='stretch')
        reviewable = {o['id']: o for o in pending if o.get('reviewable')}
        if reviewable and can('radar_review'):
            oid = st.selectbox('Observation à examiner', list(reviewable), format_func=lambda k: f'{reviewable[k]["ean"]} · {reviewable[k]["retailer"]} · {reviewable[k]["observed_at"]}', key='radar_review_id')
            st.json({'Pneu pilote': reviewable[oid].get('target_product'), 'Relevé à valider': {k: reviewable[oid].get(k) for k in ('source_ean', 'ean', 'brand', 'profile', 'dimension', 'load', 'speed', 'season', 'xl', 'runflat', 'homologation', 'url', 'price_ht', 'reasons')}})
            note = st.text_input('Justification de la décision', key='radar_review_note')
            a, b = st.columns(2)
            decision = True if a.button('Valider cette observation', disabled=not note.strip(), key='radar_approve') else False if b.button('Rejeter cette observation', disabled=not note.strip(), key='radar_reject') else None
            if decision is not None:
                try:
                    database.review(oid, decision, user, note, workspace)
                    st.session_state.notice = 'Décision enregistrée ; les grilles publiées sont conservées.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error('La décision n’a pas pu être enregistrée.')
        st.caption('Une identité incohérente, une prestation incluse ou un prix invalide doivent être corrigés dans la source. Leur validation forcée est bloquée.')
        for report in runs:
            with st.expander(f'{report["started_at"][:19]} · {report["references"]} références' + (' · SIMULATION' if report.get('simulated') else '')):
                st.dataframe(pd.DataFrame(report['connectors']), hide_index=True, width='stretch')
