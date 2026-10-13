"""Streamlit V1 — app indépendante de GPT et Base44."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from eurotyre.engine import demo, calculate, rule_conflicts, SEASONS, DIAMETER_BANDS, decimal, norm
from eurotyre.imports import read_upload, import_rows, guess, FIELDS, LABELS
from eurotyre.exports import template, excel_bytes, csv_bytes, export_frame, pricing_export_frame
from eurotyre.analytics import price_indicators, summarize, overall_market_gap
from eurotyre.rules_grid import cell_key, grid_brands, saved_discounts, market_discounts
from eurotyre.service import mutate, PERMISSIONS
from eurotyre.storage import PostgresStore, ConflictError

st.set_page_config(page_title='Outil prix Eurotyre', page_icon='🛞', layout='wide')
st.markdown('''<style>
[data-testid="stAppViewContainer"]{background:#f5f7fb} [data-testid="stSidebar"]{background:white;border-right:1px solid #e5eaf2}
h1,h2,h3{letter-spacing:-.7px;color:#183254}[data-testid="stMetric"]{background:white;border:1px solid #e5eaf2;border-radius:12px;padding:20px}
[data-testid="stMetricLabel"]{color:#718199}[data-testid="stMetricValue"]{color:#183f76}
.eyebrow{color:#155bd7;font-size:11px;font-weight:700;letter-spacing:2px}.subtitle{color:#7788a1;margin-bottom:24px}
[class*="st-key-bf_grid_row_"] [data-testid="stNumberInputField"]{padding-left:6px;padding-right:4px}
</style>''', unsafe_allow_html=True)

def config():
    try:
        return st.secrets.to_dict()
    except FileNotFoundError:
        return {}

cfg = config()
mode = cfg.get('app', {}).get('mode', 'demo')
if mode not in ('demo', 'production'):
    st.error('Mode non reconnu. Choisir demo ou production dans les Secrets.')
    st.stop()
store = None
role, user = 'admin', 'Session de démonstration'
if mode == 'production':
    if not cfg.get('auth') or not cfg.get('database', {}).get('url'):
        st.error('Accès fermé : configure la connexion et la base avant de charger les données réelles.')
        st.stop()
    if not st.user.is_logged_in:
        st.title('Eurotyre Pricing Manager')
        st.write('Connecte-toi pour accéder à ton espace tarifaire.')
        st.button('Se connecter', on_click=st.login, type='primary')
        st.stop()
    email = str(st.user.get('email', '')).lower()
    if st.user.get('email_verified') is False:
        st.error('Adresse non vérifiée. Accès refusé.')
        st.stop()
    role = next((r for r in ('admin', 'pricing', 'viewer') if email and email in [str(x).lower() for x in cfg.get('roles', {}).get(r, [])]), '')
    if not role:
        st.error('Ton compte ne figure pas parmi les utilisateurs autorisés.')
        st.button('Se déconnecter', on_click=st.logout)
        st.stop()
    user = str(st.user.get('name', email))
    store = PostgresStore(cfg['database']['url'])
    try:
        state = store.load(cfg.get('app', {}).get('workspace', 'eurotyre'))
    except Exception:
        st.error('La base de données n’est pas disponible. Vérifie sa connexion et applique schema_postgres.sql.')
        st.stop()
else:
    if 'pricing_state' not in st.session_state:
        st.session_state.pricing_state = demo()
    state = deepcopy(st.session_state.pricing_state)

with st.sidebar:
    st.image(str(Path(__file__).parent/'assets'/'eurotyre_logo.png'), width='stretch', alt='Eurotyre — Pneus et services')
    st.caption('PILOTAGE DES PRIX HT')
    st.divider()
    tab = st.radio('Pilotage tarifaire', ['Vue d’ensemble', 'Imports & rapprochement', 'Règles tarifaires', 'Catalogue', 'Export', 'Versions & diffusion', 'Guide & historique'])
    st.divider()
    st.caption({'admin': 'Administrateur', 'pricing': 'Responsable Pricing', 'viewer': 'Consultation'}[role])
    st.write(user)
    if mode == 'production':
        st.button('Se déconnecter', on_click=st.logout)
    else:
        st.info('Démo · données fictives · sauvegarde limitée à cette session.')

st.markdown('<div class="eyebrow">EUROTYRE / PRICING</div>', unsafe_allow_html=True)
st.title('Outil prix Eurotyre' if tab == 'Vue d’ensemble' else tab)
st.markdown('<div class="subtitle">Recommandations de prix publics HT · Pneumatiques tourisme, camionnette et SUV</div>', unsafe_allow_html=True)
if mode == 'demo':
    st.warning('DÉMONSTRATION — données fictives uniquement. Les modifications ne survivent pas à la fermeture complète de la session. Le mode production utilise PostgreSQL et une connexion contrôlée.')
if st.session_state.get('notice'):
    st.success(st.session_state.pop('notice'))

rows = calculate(state)
matched = [r for r in rows if r['market_price'] is not None]
alerts = [r for r in rows if r['alerts']]
can = lambda action: action in PERMISSIONS[role]

def execute(action, **params):
    try:
        changed = mutate(state, action, role, user, **params)
        if store:
            store.save(changed, state['revision'], cfg.get('app', {}).get('workspace', 'eurotyre'))
        else:
            changed['revision'] += 1
            st.session_state.pricing_state = changed
        if action == 'bf_grid':
            st.session_state.pop('bf_grid_draft', None)
        st.session_state.notice = 'Modification enregistrée.'
        st.rerun()
    except (ValueError, PermissionError) as e:
        st.error(str(e))
    except Exception:
        st.error('La sauvegarde a échoué. Aucune confirmation d’enregistrement n’a été reçue ; recharge la page avant de recommencer.')

def filtered(items):
    a, b, c, d, e = st.columns([2, 1.4, 1.4, 1, 1])
    search = a.text_input('Rechercher', placeholder='EAN, dimension ou marque…')
    brand = b.selectbox('Marque', ['Toutes'] + sorted({r['brand'] for r in items}))
    seas = c.selectbox('Saison', ['Toutes'] + list(SEASONS))
    diameter = d.selectbox('Diamètre', ['Tous'] + sorted({r['diameter'] for r in items}))
    only_alerts = e.checkbox('Anomalies uniquement')
    return [r for r in items if (not search or search.lower() in ' '.join(str(r[k]) for k in ('ean', 'ref', 'brand', 'dimension')).lower()) and (brand == 'Toutes' or brand == r['brand']) and (seas == 'Toutes' or seas == r['season']) and (diameter == 'Tous' or diameter == r['diameter']) and (not only_alerts or r['alerts'])]

def catalogue(items):
    records = []
    for r in items:
        record = {k: r.get(k) for k in ('brand', 'dimension', 'season', 'ean', 'bf', 'market_price', 'variation', 'recommended', 'delta', 'rule', 'match')}
        record.update(price_indicators(r))
        for k in ('bf', 'market_price', 'variation', 'recommended', 'delta', 'market_discount', 'retailer_discount', 'market_gap'):
            record[k] = float(record[k]) if record[k] is not None else None
        record['alerts'] = ' · '.join(r['alerts']) or 'Conforme'
        records.append(record)
    names = {'brand': 'Marque', 'dimension': 'Dimension', 'season': 'Saison', 'ean': 'EAN', 'bf': 'BF HT', 'market_price': 'Marché HT', 'variation': 'Variation %', 'recommended': 'Prix commerçant Eurotyre HT', 'delta': 'Écart €', 'market_discount': 'Remise marché / BF (%)', 'retailer_discount': 'Remise commerçant / BF (%)', 'market_gap': 'Écart commerçant / marché (%)', 'rule': 'Règle', 'match': 'Rapprochement', 'alerts': 'Contrôle'}
    st.caption(f"{len(items)} {'référence' if len(items) == 1 else 'références'} · EUR HT")
    st.dataframe(pd.DataFrame(records).rename(columns=names), hide_index=True, width='stretch', height=480)

if tab == 'Vue d’ensemble':
    season_summary = summarize(rows)
    brand_summary = summarize(rows, by_season=False)
    compared_count = sum(item['compared'] for item in brand_summary)
    global_gap = overall_market_gap(rows)
    st.subheader('Écart des prix vs marché')
    indicators = st.columns(4)
    for indicator, season_name in zip(indicators, SEASONS):
        season_gap = overall_market_gap([row for row in rows if row['season'] == season_name])
        indicator.metric(season_name, f'{Decimal(season_gap):+.2f} %' if season_gap is not None else '—')
    indicators[3].metric('Total', f'{Decimal(global_gap):+.2f} %' if global_gap is not None else '—')
    st.caption('Toutes marques · moyenne des écarts par référence comparable. Total = ensemble des saisons. + = au-dessus du marché ; − = en dessous.')
    st.subheader('Remises moyennes par marque et saison')
    st.caption('Remise vs BF HT = (1 − prix HT / BF HT) × 100. Les remises et l’écart Eurotyre/marché sont des moyennes sur les mêmes références comparables, sans pondération de volume.')
    brand_filter, season_filter = st.columns(2)
    selected_brand = brand_filter.selectbox('Marque', ['Toutes les marques'] + sorted({item['brand'] for item in season_summary}), key='overview_brand')
    selected_season = season_filter.selectbox('Saison', ['Toutes les saisons'] + list(SEASONS), key='overview_season')
    selected_summary = [item for item in season_summary
                        if (selected_brand == 'Toutes les marques' or item['brand'] == selected_brand)
                        and (selected_season == 'Toutes les saisons' or item['season'] == selected_season)]
    season_frame = pd.DataFrame([{
        'Marque': item['brand'], 'Saison': item['season'],
        'Écart Eurotyre / marché (%)': float(item['market_gap']) if item['market_gap'] is not None else None,
        'Marché / BF (%)': float(item['market_discount']) if item['market_discount'] is not None else None,
        'Commerçant / BF (%)': float(item['retailer_discount']) if item['retailer_discount'] is not None else None,
    } for item in selected_summary], columns=['Marque', 'Saison', 'Écart Eurotyre / marché (%)', 'Marché / BF (%)', 'Commerçant / BF (%)'])
    st.dataframe(season_frame, hide_index=True, width='stretch', height=400, column_config={
        'Écart Eurotyre / marché (%)': st.column_config.NumberColumn(format='%+.2f %%', help='Écart moyen des prix Eurotyre vs marché : moyenne de (prix Eurotyre HT / prix marché HT − 1) × 100.'),
        'Marché / BF (%)': st.column_config.NumberColumn(format='%.2f %%', help='Moyenne des remises (1 − prix marché HT / BF HT) × 100.'),
        'Commerçant / BF (%)': st.column_config.NumberColumn(format='%.2f %%', help='Moyenne des remises (1 − prix commerçant Eurotyre HT / BF HT) × 100.'),
    })
    if season_frame.empty:
        st.caption('Aucune référence pour cette sélection de marque et saison.')
    if compared_count < len(rows):
        st.info(f'{len(rows) - compared_count} références sans comparaison complète : BF, prix marché et prix commerçant calculé sont nécessaires. Les valeurs absentes ne sont pas remplacées par zéro.')
    st.subheader('Écart moyen commerçant / marché par marque')
    st.caption('Écart = (prix commerçant Eurotyre HT / prix marché HT − 1) × 100, puis moyenne par marque, toutes saisons confondues. + = au-dessus du marché ; − = en dessous.')
    brand_frame = pd.DataFrame([{
        'Marque': item['brand'],
        'Écart moyen (%)': float(item['market_gap']) if item['market_gap'] is not None else None,
    } for item in brand_summary], columns=['Marque', 'Écart moyen (%)'])
    left, right = st.columns([1.15, 1])
    with left:
        st.dataframe(brand_frame, hide_index=True, width='stretch', column_config={
            'Écart moyen (%)': st.column_config.NumberColumn(format='%+.2f %%')
        })
    with right:
        chart = brand_frame.dropna(subset=['Écart moyen (%)']).set_index('Marque')
        if not chart.empty:
            st.bar_chart(chart[['Écart moyen (%)']], color='#D4B000', horizontal=True, height=280)
        else:
            st.info('Aucune référence comparable à afficher.')
    st.subheader('Catalogue & recommandations')
    catalogue(filtered(rows))

elif tab == 'Imports & rapprochement':
    st.info('Un import valide remplace le référentiel courant du même type. Chaque import conserve une copie de ses lignes normalisées dans l’historique.')
    kind_name = st.selectbox('Référentiel à charger', ['Barème fournisseur (BF)', 'Prix de marché HT'])
    kind = 'bf' if kind_name.startswith('Barème') else 'market'
    a, b = st.columns(2)
    frame = template(kind)
    a.download_button('Modèle Excel — données fictives', excel_bytes(frame), file_name=f'{kind}_demo.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    b.download_button('Modèle CSV — données fictives', csv_bytes(frame), file_name=f'{kind}_demo.csv', mime='text/csv')
    upload = st.file_uploader('Charger un fichier XLSX ou CSV', type=['xlsx', 'csv'], disabled=not can('import'))
    if upload:
        try:
            data, sheets = read_upload(upload.getvalue(), upload.name)
            if sheets:
                selected = st.selectbox('Feuille Excel', sheets)
                data, _ = read_upload(upload.getvalue(), upload.name, selected)
            st.subheader('Associer les colonnes')
            mapping, guessed = {}, guess(data.columns, kind)
            columns = st.columns(3)
            options = ['Non fourni'] + list(data.columns)
            for i, field in enumerate(FIELDS[kind]):
                chosen = columns[i % 3].selectbox(LABELS[field], options, index=options.index(guessed[field]) if guessed[field] else 0, key=f'map_{kind}_{upload.name}_{field}')
                mapping[field] = '' if chosen == 'Non fourni' else chosen
            st.caption('Dimensions : renseigner la colonne Dimension ou les trois colonnes Largeur / Série / Diamètre.')
            st.dataframe(data.head(5), hide_index=True, width='stretch')
            imported, errors = import_rows(data.to_dict('records'), mapping, kind)
            if errors:
                st.error(f'{len(errors)} lignes invalides : l’import complet est bloqué.')
                st.write(errors[:30])
            else:
                st.success(f'{len(imported)} lignes conformes.')
            fictional = st.checkbox('Je confirme que ce fichier contient uniquement des données fictives', value=False) if mode == 'demo' else True
            if st.button('Contrôler et importer', disabled=bool(errors) or not fictional or not can('import'), type='primary'):
                execute('import', rows=data.to_dict('records'), mapping=mapping, kind=kind, name=upload.name)
        except Exception as e:
            st.error(f'Lecture impossible : {e}')
    st.subheader('Rapprochement')
    st.metric('Références avec prix marché unique', f'{len(matched)} / {len(rows)}')
    st.caption('EAN prioritaire, puis marque + dimension + saison et référence fabricant ou charge/vitesse. Les ambiguïtés bloquent le calcul.')
    st.subheader('Historique des imports')
    if not state['imports']:
        st.caption('Aucun import utilisateur ; jeu fictif initial chargé.')
    for i, item in enumerate(state['imports']):
        with st.expander(f"{item['name']} · {item['count']} lignes · {item['date'][:19]}"):
            st.dataframe(pd.DataFrame(item['rows']).drop(columns=['id'], errors='ignore'), hide_index=True, width='stretch')

elif tab == 'Règles tarifaires':
    st.markdown('**Remises BF à appliquer (%)**')
    st.caption('Prix Eurotyre HT = BF HT × (1 − remise / 100). Une cellule vide conserve la règle actuelle ; 0 % applique le BF sans remise.')
    st.caption('Sous chaque ligne : remise moyenne marché / BF, en lecture seule. « — » indique qu’aucun prix marché comparable n’est disponible. Les saisies sont conservées quand tu changes de filtre ; enregistre pour les appliquer.')
    brands = grid_brands(state)
    saved = saved_discounts(state['rules'])
    reference = market_discounts(rows)
    draft = st.session_state.setdefault('bf_grid_draft', {})
    widths = [1.8, 1.7, 1, 1, 1, 1, 1, 1.1]
    header = st.columns(widths, gap='small')
    brand_filter = header[0].selectbox('Marque', ['Toutes les marques'] + brands, key='rules_brand')
    season_filter = header[1].selectbox('Saison', ['Toutes les saisons'] + list(SEASONS), key='rules_season')
    for column, (label, _, _) in zip(header[2:], DIAMETER_BANDS):
        column.markdown(f'**{label}**')
        column.caption('%')
    if not brands:
        st.info('Importe un catalogue BF pour renseigner les remises par marque.')
    for brand in brands:
        if brand_filter != 'Toutes les marques' and norm(brand_filter) != norm(brand):
            continue
        for seas in SEASONS:
            if season_filter != 'Toutes les saisons' and season_filter != seas:
                continue
            with st.container(border=True, key=f'bf_grid_row_{cell_key(brand, seas, 13, 30)}'):
                line = st.columns(widths, gap='small')
                line[0].write(f'**{brand}**')
                line[1].write(seas)
                for column, (label, low, high) in zip(line[2:], DIAMETER_BANDS):
                    key = cell_key(brand, seas, low, high)
                    initial = draft[key]['discount'] if key in draft else saved.get(key)
                    widget_key = f'bf_cell_{state["revision"]}_{key}'
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = float(initial) if initial is not None else None
                    value = column.number_input(
                        f'Remise BF {brand} {seas} {label}', min_value=0., max_value=99.99,
                        value=None, step=.1, format='%.2f',
                        placeholder='—', label_visibility='collapsed', disabled=not can('bf_grid'),
                        key=widget_key)
                    if decimal(value) != decimal(saved.get(key)):
                        draft[key] = {'brand': brand, 'season': seas, 'min': low, 'max': high,
                                      'discount': str(value) if value is not None else None}
                    else:
                        draft.pop(key, None)
                market_line = st.columns(widths, gap='small')
                market_line[0].caption('Marché (info)')
                market_line[1].caption(seas)
                for column, (_, low, high) in zip(market_line[2:], DIAMETER_BANDS):
                    observed = reference.get(cell_key(brand, seas, low, high))
                    column.caption(f'{observed.replace(".", ",")} %' if observed is not None else '—')
    st.caption(f'{len(draft)} cellule(s) modifiée(s), tous filtres confondus.')
    if st.button('Enregistrer les remises BF', disabled=not can('bf_grid') or not draft, type='primary'):
        execute('bf_grid', changes=list(draft.values()))
    conflicts = rule_conflicts(state['rules'])
    if conflicts:
        st.error('Conflits bloquants : '+', '.join(conflicts))
    st.caption('Les remises BF renseignées sont prioritaires. Les règles déjà enregistrées restent utilisées pour les cellules vides.')
    st.subheader('Seuils de contrôle')
    with st.form('settings'):
        deviation = st.number_input('Écart absolu maximum au marché (%)', min_value=0., max_value=100., value=float(state['settings']['max_deviation']))
        if st.form_submit_button('Enregistrer les seuils', disabled=not can('settings')):
            execute('settings', max_deviation=deviation)

elif tab == 'Catalogue':
    catalogue(filtered(rows))

elif tab == 'Export':
    export_rows, export_rules = rows, state['rules']
    filename = 'Eurotyre_tarif_courant'
    st.caption('Prix Eurotyre HT et remises BF · format Excel ou CSV.')
    if role == 'viewer':
        available = {v['id']: v for v in state['versions'] if v['status'] in ('Validée', 'Publiée')}
        if available:
            selected = st.selectbox('Version à exporter', list(available), key='export_version')
            version = available[selected]
            export_rows, export_rules = version['rows'], version['rules']
            filename = f'Eurotyre_{selected}'
        else:
            export_rows = []
            st.info('Aucune version validée à exporter.')
    else:
        st.caption('Tarif courant · remises enregistrées.')
    exported = pricing_export_frame(export_rows, export_rules)
    excluded = len(export_rows) - len(exported)
    st.caption(f'{len(exported)} références avec un prix calculé · EUR HT')
    if excluded:
        st.info(f'{excluded} références sans prix calculé sont exclues de cet export.')
    missing_ean = int(exported['Code EAN'].eq('').sum())
    if missing_ean:
        st.warning(f'{missing_ean} références sans code EAN renseigné dans le catalogue.')
    excel_column, csv_column, _ = st.columns([1, 1, 3])
    excel_column.download_button('Télécharger Excel', excel_bytes(exported),
        file_name=f'{filename}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        disabled=exported.empty, key='compact_export_xlsx')
    csv_column.download_button('Télécharger CSV', csv_bytes(exported),
        file_name=f'{filename}.csv', mime='text/csv', disabled=exported.empty, key='compact_export_csv')
    st.dataframe(exported, hide_index=True, width='stretch', height=480, column_config={
        'Code EAN': st.column_config.TextColumn(help='Code conservé en texte, y compris les zéros initiaux.'),
        'Prix HT': st.column_config.NumberColumn(format='%.2f €', help='Prix Eurotyre HT calculé.'),
        'Remise BF (%)': st.column_config.NumberColumn(format='%.2f %%',
            help='Remise BF renseignée ; pour une ancienne règle, remise équivalente : (1 − prix Eurotyre HT / BF HT) × 100.'),
    })

elif tab == 'Versions & diffusion':
    st.info('Brouillon → contrôle et validation → publication interne. Toute anomalie est bloquante dans cette V1. Aucun envoi aux franchisés ou aux ERP n’est déclenché.')
    if st.button('Créer un brouillon', disabled=not can('version'), type='primary'):
        execute('version')
    for version in state['versions']:
        with st.container(border=True):
            st.subheader(f"{version['id']} · {version['status']}")
            st.caption(f"{version['date'][:19]} · {len(version['rows'])} références · {sum(bool(r['alerts']) for r in version['rows'])} anomalies")
            if version['status'] == 'Brouillon':
                if st.button('Contrôler et valider', key=f"validate_{version['id']}", disabled=not can('validate')):
                    execute('validate', id=version['id'])
                st.caption('Après correction des données ou règles, créer un nouveau brouillon : cet instantané reste archivé.')
            else:
                a, b, c = st.columns(3)
                exported = export_frame(version)
                a.download_button('Export Excel', excel_bytes(exported), file_name=f"Eurotyre_{version['id']}.xlsx", key=f"xlsx_{version['id']}")
                b.download_button('Export CSV', csv_bytes(exported), file_name=f"Eurotyre_{version['id']}.csv", key=f"csv_{version['id']}")
                if version['status'] == 'Validée' and c.button('Publier en interne', key=f"pub_{version['id']}", disabled=not can('publish')):
                    execute('publish', id=version['id'])
    if not state['versions']:
        st.caption('Aucune version préparée.')

elif tab == 'Guide & historique':
    st.markdown('''1. Télécharger les modèles et importer BF puis prix marché.
2. Vérifier les colonnes, les dimensions et les références.
3. Dans Règles tarifaires, choisir la marque et la saison en tête de grille, saisir les remises BF par tranche de diamètre, puis enregistrer. La ligne Marché sous chaque saisie indique la remise BF moyenne constatée, sans être modifiable.
4. Contrôler les anomalies dans le catalogue.
5. Créer un brouillon, valider sans anomalie, puis publier en interne.
6. Dans Export, télécharger le tarif en Excel ou CSV : Marque, Saison, Code EAN, Prix HT Eurotyre et Remise BF (%). Les références sans prix calculé sont exclues. Le profil Consultation exporte uniquement les versions validées ou publiées.

**Vue d’ensemble.** Les remises marché/BF et commerçant/BF sont calculées par marque et saison : (1 − prix HT / BF HT) × 100. L’écart commerçant/marché est calculé par marque : (prix commerçant HT / prix marché HT − 1) × 100. Les indicateurs sont des moyennes par référence, sur les mêmes références comparables. Un écart positif indique un prix commerçant au-dessus du marché. Les prix absents sont exclus, jamais remplacés par zéro.

**Rapprochement conservateur.** Sans EAN, la marque, la dimension et la saison ne suffisent pas : une référence fabricant ou les indices charge/vitesse sont requis. Les prix de marché ne sont jamais inventés.

**Persistance.** Démo : session isolée et données fictives. Production : PostgreSQL externe et authentification OIDC, avec rôles attribués dans les Secrets. Le stockage local de Streamlit Cloud n’est pas utilisé pour conserver des données réelles.

**Identité graphique.** Logo Eurotyre fourni, intégré dans la navigation.''')
    if role == 'admin':
        st.download_button('Sauvegarder l’espace (JSON)', json.dumps(state, ensure_ascii=False, indent=2).encode(), file_name='Eurotyre_sauvegarde.json', mime='application/json')
    st.subheader('Journal d’activité')
    st.dataframe(pd.DataFrame(state['audit']), hide_index=True, width='stretch')
    for name in ('GUIDE_UTILISATEUR.md', 'DEPLOIEMENT.md'):
        path = Path(__file__).parent/'docs'/name
        if path.exists():
            st.download_button(name.replace('_', ' ').replace('.md',''), path.read_bytes(), file_name=name)

st.divider()
st.caption('Outil prix Eurotyre · Prix publics commerçants HT · Données initiales fictives')

