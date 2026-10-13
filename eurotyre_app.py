"""Streamlit V1 — app indépendante de GPT et Base44."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from eurotyre.engine import demo, calculate, rule_conflicts, SEASONS
from eurotyre.imports import read_upload, import_rows, guess, FIELDS, LABELS
from eurotyre.exports import template, excel_bytes, csv_bytes, export_frame
from eurotyre.service import mutate, PERMISSIONS
from eurotyre.storage import PostgresStore, ConflictError

st.set_page_config(page_title='Eurotyre · Pricing Manager', page_icon='🛞', layout='wide')
st.markdown('''<style>
[data-testid="stAppViewContainer"]{background:#f5f7fb} [data-testid="stSidebar"]{background:white;border-right:1px solid #e5eaf2}
h1,h2,h3{letter-spacing:-.7px;color:#183254}[data-testid="stMetric"]{background:white;border:1px solid #e5eaf2;border-radius:12px;padding:20px}
[data-testid="stMetricLabel"]{color:#718199}[data-testid="stMetricValue"]{color:#183f76}
.brand{font:italic 900 32px Arial;color:#155bd7;letter-spacing:-1.6px}.brand span{color:#102f60}.underline{height:5px;width:160px;background:#ffd000;margin:4px 0 15px;transform:skew(-14deg)}
.eyebrow{color:#155bd7;font-size:11px;font-weight:700;letter-spacing:2px}.subtitle{color:#7788a1;margin-bottom:24px}.formula{background:#102f60;color:white;border-radius:12px;padding:24px;margin-bottom:20px}
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
    st.markdown('<div class="brand">EURO<span>TYRE</span></div><div class="underline"></div>', unsafe_allow_html=True)
    st.caption('PRICING MANAGER · VERSION STREAMLIT')
    st.divider()
    tab = st.radio('Pilotage tarifaire', ['Vue d’ensemble', 'Imports & rapprochement', 'Règles tarifaires', 'Simulation', 'Catalogue', 'Versions & diffusion', 'Guide & historique'])
    st.divider()
    st.caption({'admin': 'Administrateur', 'pricing': 'Responsable Pricing', 'viewer': 'Consultation'}[role])
    st.write(user)
    if mode == 'production':
        st.button('Se déconnecter', on_click=st.logout)
    else:
        st.info('Démo · données fictives · sauvegarde limitée à cette session.')

st.markdown('<div class="eyebrow">EUROTYRE / PRICING</div>', unsafe_allow_html=True)
st.title('Tes prix. Une vision claire.' if tab == 'Vue d’ensemble' else tab)
st.markdown('<div class="subtitle">Recommandations de prix publics HT · Pneumatiques tourisme, camionnette et SUV</div>', unsafe_allow_html=True)
if mode == 'demo':
    st.warning('DÉMONSTRATION — données fictives uniquement. Les modifications ne survivent pas à la fermeture complète de la session. Le mode production utilise PostgreSQL et une connexion contrôlée.')
if st.session_state.get('notice'):
    st.success(st.session_state.pop('notice'))

rows = calculate(state)
ready = [r for r in rows if r['recommended'] is not None and not r['alerts']]
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
        record = {k: r.get(k) for k in ('brand', 'dimension', 'season', 'ean', 'bf', 'net', 'market_price', 'variation', 'recommended', 'delta', 'margin_eur', 'margin', 'markup', 'rule', 'match')}
        for k in ('bf', 'net', 'market_price', 'variation', 'recommended', 'delta', 'margin_eur', 'margin', 'markup'):
            record[k] = float(record[k]) if record[k] is not None else None
        record['alerts'] = ' · '.join(r['alerts']) or 'Conforme'
        records.append(record)
    names = {'brand': 'Marque', 'dimension': 'Dimension', 'season': 'Saison', 'ean': 'EAN', 'bf': 'BF HT', 'net': 'PA net HT', 'market_price': 'Marché HT', 'variation': 'Variation %', 'recommended': 'PV recommandé HT', 'delta': 'Écart €', 'margin_eur': 'Marge brute €', 'margin': 'Taux de marque %', 'markup': 'Taux de marge %', 'rule': 'Règle', 'match': 'Rapprochement', 'alerts': 'Contrôle'}
    st.caption(f'{len(items)} références · EUR HT')
    st.dataframe(pd.DataFrame(records).rename(columns=names), hide_index=True, width='stretch', height=480)

if tab == 'Vue d’ensemble':
    a, b, c, d = st.columns(4)
    a.metric('Références au catalogue', len(rows))
    b.metric('Rapprochement marché', f'{len(matched) / len(rows) * 100:.0f} %' if rows else '0 %')
    c.metric('Prix conformes', len(ready))
    d.metric('Références à contrôler', len(alerts))
    left, right = st.columns([1.25, 1])
    with left:
        st.subheader('Positionnement au marché')
        calculated = [r for r in rows if r['recommended'] is not None]
        avg = sum(Decimal(r['variation']) for r in calculated) / len(calculated) if calculated else Decimal(0)
        st.metric('Variation moyenne non pondérée', f'{avg:+.2f} %')
        st.caption('Moyenne des règles appliquées sur les produits calculables. Les pourcentages ne se cumulent pas.')
        st.info(f'{len(alerts)} références doivent être contrôlées avant validation.')
    with right:
        st.subheader('Répartition par marque')
        st.bar_chart(pd.Series([r['brand'] for r in rows], dtype=str).value_counts(), color='#155bd7', horizontal=True)
    a, b = st.columns(2)
    with a:
        st.subheader('Par saison')
        st.bar_chart(pd.Series([r['season'] for r in rows], dtype=str).value_counts(), color='#155bd7')
    with b:
        st.subheader('Par diamètre')
        st.bar_chart(pd.Series([r['diameter'] for r in rows], dtype=int).value_counts().sort_index(), color='#E6B900')
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
    st.caption('Modifier les valeurs, puis enregistrer pour recalculer. Une règle générale utilise des critères vides ; min = max pour un diamètre unique.')
    rules_frame = pd.DataFrame(state['rules'])
    for k in ('min', 'max', 'variation'):
        rules_frame[k] = pd.to_numeric(rules_frame[k], errors='coerce')
    edited = st.data_editor(rules_frame, num_rows='dynamic', hide_index=True, width='stretch', disabled=not can('rules'), column_config={'id':st.column_config.TextColumn('Nom', required=True), 'brand':st.column_config.TextColumn('Marque (vide = toutes)'), 'min':st.column_config.NumberColumn('Diamètre min', min_value=13, max_value=30, step=1), 'max':st.column_config.NumberColumn('Diamètre max', min_value=13, max_value=30, step=1), 'season':st.column_config.SelectboxColumn('Saison', options=['']+list(SEASONS)), 'variation':st.column_config.NumberColumn('Variation %', min_value=-90, max_value=100, step=.1), 'active':st.column_config.CheckboxColumn('Active')})
    if st.button('Enregistrer les règles', disabled=not can('rules'), type='primary'):
        clean = edited.astype(object).where(pd.notna(edited), None).to_dict('records')
        execute('rules', rules=clean)
    conflicts = rule_conflicts(state['rules'])
    if conflicts:
        st.error('Conflits bloquants : '+', '.join(conflicts))
    st.write('**Priorité :** marque + diamètre + saison → marque + diamètre → marque + saison → marque → générale.')
    st.subheader('Seuils de contrôle')
    with st.form('settings'):
        a, b = st.columns(2)
        minimum = a.number_input('Taux de marque minimum (%)', min_value=0., max_value=99., value=float(state['settings']['min_margin']))
        deviation = b.number_input('Écart absolu maximum au marché (%)', min_value=0., max_value=100., value=float(state['settings']['max_deviation']))
        if st.form_submit_button('Enregistrer les seuils', disabled=not can('settings')):
            execute('settings', min_margin=minimum, max_deviation=deviation)

elif tab == 'Simulation':
    st.markdown('<div class="formula"><b>PV recommandé HT = prix marché HT × (1 + variation / 100)</b></div>', unsafe_allow_html=True)
    st.caption('Le scénario de référence fige ses règles. Il est comparé au scénario actuel sur les mêmes données courantes.')
    if st.button('Figer le scénario de référence', disabled=not can('baseline')):
        execute('baseline')
    base = {r['id']:r for r in calculate(state, state['baseline'])}
    compared = []
    for r in filtered(rows):
        pv = r['recommended']
        old = base[r['id']]['recommended']
        compared.append({'Marque':r['brand'], 'Dimension':r['dimension'], 'Saison':r['season'], 'EAN':r['ean'], 'PV référence HT':float(old) if old else None, 'PV actuel HT':float(pv) if pv else None, 'Impact €':float(Decimal(pv)-Decimal(old)) if pv and old else None, 'Taux de marque %':float(r['margin']) if r['margin'] else None})
    st.dataframe(pd.DataFrame(compared), hide_index=True, width='stretch', height=480)

elif tab == 'Catalogue':
    catalogue(filtered(rows))

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
3. Paramétrer une variation par marque, diamètre et saison, puis enregistrer.
4. Contrôler les anomalies et comparer les scénarios.
5. Créer un brouillon, valider sans anomalie, puis publier en interne.
6. Exporter la version validée en CSV ou Excel.

**BF ≠ PA net.** Sans prix d’achat net réel, les marges restent absentes. Marge brute = PV − PA ; taux de marque = marge / PV ; taux de marge = marge / PA. Les prix sont arrondis au centime avec Decimal, demi supérieur.

**Rapprochement conservateur.** Sans EAN, la marque, la dimension et la saison ne suffisent pas : une référence fabricant ou les indices charge/vitesse sont requis. Les prix de marché ne sont jamais inventés.

**Persistance.** Démo : session isolée et données fictives. Production : PostgreSQL externe et authentification OIDC, avec rôles attribués dans les Secrets. Le stockage local de Streamlit Cloud n’est pas utilisé pour conserver des données réelles.

**Identité graphique.** En-tête typographique provisoire ; logo Eurotyre officiel à intégrer lorsqu’il sera fourni.''')
    if role == 'admin':
        st.download_button('Sauvegarder l’espace (JSON)', json.dumps(state, ensure_ascii=False, indent=2).encode(), file_name='Eurotyre_sauvegarde.json', mime='application/json')
    st.subheader('Journal d’activité')
    st.dataframe(pd.DataFrame(state['audit']), hide_index=True, width='stretch')
    for name in ('GUIDE_UTILISATEUR.md', 'DEPLOIEMENT.md'):
        path = Path(__file__).parent/'docs'/name
        if path.exists():
            st.download_button(name.replace('_', ' ').replace('.md',''), path.read_bytes(), file_name=name)

st.divider()
st.caption('Eurotyre Pricing Manager · V1 Streamlit · Prix publics recommandés HT · Données initiales fictives')
