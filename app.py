import re
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Pricing Cockpit Pneumatiques",
    page_icon="🛞",
    layout="wide"
)

st.markdown("""
<style>
    .main {
        background-color: #f7f8fa;
    }
    .kpi-card {
        background-color: white;
        padding: 22px;
        border-radius: 18px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        text-align: center;
    }
    .kpi-title {
        font-size: 14px;
        color: #666;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 700;
        color: #1f2937;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# FUNCTIONS
# ============================================================

def normalize_dimension(value):
    if pd.isna(value):
        return np.nan

    txt = str(value).upper()
    txt = txt.replace(" ", "")
    txt = txt.replace("-", "")
    txt = txt.replace("_", "")
    txt = txt.replace("ZR", "R")

    match = re.search(r"(\d{3})/?(\d{2})R?(\d{2})", txt)

    if match:
        width = match.group(1)
        height = match.group(2)
        rim = match.group(3)
        return f"{width}/{height}R{rim}"

    return txt


def read_file(uploaded_file):
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, sep=None, engine="python")
    return pd.read_excel(uploaded_file)


def format_pct(value):
    if pd.isna(value):
        return "-"
    return f"{value:.1f} %"


def format_eur(value):
    if pd.isna(value):
        return "-"
    return f"{value:,.2f} €".replace(",", " ")


# ============================================================
# HEADER
# ============================================================

st.title("🛞 Pricing Cockpit Pneumatiques")
st.caption("Analyse BF manufacturiers, remises achat, remises de vente et marge par marque / dimension / segment")


# ============================================================
# SIDEBAR UPLOADS
# ============================================================

st.sidebar.header("📥 Données à importer")

bf_file = st.sidebar.file_uploader(
    "1. Barèmes manufacturiers",
    type=["csv", "xlsx"]
)

achat_file = st.sidebar.file_uploader(
    "2. Remises achat",
    type=["csv", "xlsx"]
)

vente_file = st.sidebar.file_uploader(
    "3. Remises vente BF",
    type=["csv", "xlsx"]
)

top_dim_file = st.sidebar.file_uploader(
    "4. Top dimensions marché",
    type=["csv", "xlsx"]
)

st.sidebar.markdown("---")
st.sidebar.info("Formats attendus : CSV ou Excel")


# ============================================================
# EMPTY STATE
# ============================================================

if not all([bf_file, achat_file, vente_file, top_dim_file]):
    st.warning("Importe les 4 fichiers pour lancer l’analyse.")

    st.markdown("""
    ### Structure attendue des fichiers

    **barèmes manufacturiers**
    ```text
    marque | article | profil | dimension | segment | bf
    ```

    **remises achat**
    ```text
    marque | segment | remise_achat_pct
    ```

    **remises vente**
    ```text
    marque | segment | remise_vente_bf_pct
    ```

    **top dimensions marché**
    ```text
    dimension_base | poids_marche_pct
    ```
    """)

    st.stop()


# ============================================================
# LOAD DATA
# ============================================================

bf = read_file(bf_file)
achat = read_file(achat_file)
vente = read_file(vente_file)
top_dim = read_file(top_dim_file)

# Normalisation noms colonnes
for df in [bf, achat, vente, top_dim]:
    df.columns = [
        str(c).strip().lower()
        .replace(" ", "_")
        .replace("%", "pct")
        for c in df.columns
    ]

# ============================================================
# REQUIRED COLUMNS
# ============================================================

required_bf = {"marque", "article", "profil", "dimension", "segment", "bf"}
required_achat = {"marque", "segment", "remise_achat_pct"}
required_vente = {"marque", "segment", "remise_vente_bf_pct"}
required_top = {"dimension_base", "poids_marche_pct"}

if not required_bf.issubset(bf.columns):
    st.error(f"Colonnes manquantes dans barèmes manufacturiers : {required_bf - set(bf.columns)}")
    st.stop()

if not required_achat.issubset(achat.columns):
    st.error(f"Colonnes manquantes dans remises achat : {required_achat - set(achat.columns)}")
    st.stop()

if not required_vente.issubset(vente.columns):
    st.error(f"Colonnes manquantes dans remises vente : {required_vente - set(vente.columns)}")
    st.stop()

if not required_top.issubset(top_dim.columns):
    st.error(f"Colonnes manquantes dans top dimensions : {required_top - set(top_dim.columns)}")
    st.stop()


# ============================================================
# CLEANING
# ============================================================

bf["marque"] = bf["marque"].astype(str).str.strip()
bf["segment"] = bf["segment"].astype(str).str.strip().str.lower()
bf["dimension_base"] = bf["dimension"].apply(normalize_dimension)
bf["bf"] = pd.to_numeric(bf["bf"], errors="coerce")

achat["marque"] = achat["marque"].astype(str).str.strip()
achat["segment"] = achat["segment"].astype(str).str.strip().str.lower()
achat["remise_achat_pct"] = pd.to_numeric(achat["remise_achat_pct"], errors="coerce")

vente["marque"] = vente["marque"].astype(str).str.strip()
vente["segment"] = vente["segment"].astype(str).str.strip().str.lower()
vente["remise_vente_bf_pct"] = pd.to_numeric(vente["remise_vente_bf_pct"], errors="coerce")

top_dim["dimension_base"] = top_dim["dimension_base"].apply(normalize_dimension)
top_dim["poids_marche_pct"] = pd.to_numeric(top_dim["poids_marche_pct"], errors="coerce")


# ============================================================
# MERGE
# ============================================================

df = bf.merge(
    achat,
    on=["marque", "segment"],
    how="left"
)

df = df.merge(
    vente,
    on=["marque", "segment"],
    how="left"
)

df = df.merge(
    top_dim,
    on="dimension_base",
    how="left"
)

df["poids_marche_pct"] = df["poids_marche_pct"].fillna(0)


# ============================================================
# CALCULATIONS
# ============================================================

df["prix_achat_net"] = df["bf"] * (1 - df["remise_achat_pct"] / 100)
df["prix_vente"] = df["bf"] * (1 - df["remise_vente_bf_pct"] / 100)
df["marge_eur"] = df["prix_vente"] - df["prix_achat_net"]
df["marge_pct"] = np.where(
    df["prix_vente"] > 0,
    df["marge_eur"] / df["prix_vente"] * 100,
    np.nan
)

df["alerte"] = np.select(
    [
        df["marge_eur"] < 0,
        df["marge_pct"] < 15,
        df["marge_pct"] < 25
    ],
    [
        "🔴 Marge négative",
        "🟠 Marge faible",
        "🟡 À surveiller"
    ],
    default="🟢 OK"
)


# ============================================================
# FILTERS
# ============================================================

st.sidebar.header("🔎 Filtres")

marques = sorted(df["marque"].dropna().unique())
segments = sorted(df["segment"].dropna().unique())

selected_marques = st.sidebar.multiselect(
    "Marques",
    marques,
    default=marques
)

selected_segments = st.sidebar.multiselect(
    "Segments",
    segments,
    default=segments
)

df_filtered = df[
    df["marque"].isin(selected_marques)
    & df["segment"].isin(selected_segments)
].copy()


# ============================================================
# KPI
# ============================================================

total_articles = len(df_filtered)
avg_margin_eur = df_filtered["marge_eur"].mean()
avg_margin_pct = df_filtered["marge_pct"].mean()

weighted_df = df_filtered[df_filtered["poids_marche_pct"] > 0].copy()

if not weighted_df.empty:
    weighted_margin_eur = np.average(
        weighted_df["marge_eur"],
        weights=weighted_df["poids_marche_pct"]
    )
    weighted_margin_pct = np.average(
        weighted_df["marge_pct"],
        weights=weighted_df["poids_marche_pct"]
    )
else:
    weighted_margin_eur = np.nan
    weighted_margin_pct = np.nan

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Articles analysés</div>
        <div class="kpi-value">{total_articles}</div>
    </div>
    """, unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Marge moyenne €</div>
        <div class="kpi-value">{format_eur(avg_margin_eur)}</div>
    </div>
    """, unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Marge moyenne %</div>
        <div class="kpi-value">{format_pct(avg_margin_pct)}</div>
    </div>
    """, unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-title">Marge pondérée marché</div>
        <div class="kpi-value">{format_eur(weighted_margin_eur)}</div>
    </div>
    """, unsafe_allow_html=True)


st.markdown("---")


# ============================================================
# SUMMARY BY BRAND
# ============================================================

brand_summary = (
    df_filtered
    .groupby("marque", as_index=False)
    .agg(
        marge_moyenne_eur=("marge_eur", "mean"),
        marge_moyenne_pct=("marge_pct", "mean"),
        prix_achat_moyen=("prix_achat_net", "mean"),
        prix_vente_moyen=("prix_vente", "mean"),
        nb_articles=("article", "count")
    )
    .sort_values("marge_moyenne_eur", ascending=False)
)

st.subheader("📊 Marge moyenne € par marque")

fig_brand_margin = px.bar(
    brand_summary,
    x="marque",
    y="marge_moyenne_eur",
    text="marge_moyenne_eur",
    title="Marge moyenne en € par marque"
)

fig_brand_margin.update_traces(
    texttemplate="%{text:.2f} €",
    textposition="outside"
)

fig_brand_margin.update_layout(
    height=460,
    xaxis_title="Marque",
    yaxis_title="Marge moyenne €",
    plot_bgcolor="white",
    paper_bgcolor="white"
)

st.plotly_chart(fig_brand_margin, use_container_width=True)


# ============================================================
# TWO CHARTS
# ============================================================

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("📈 Marge % par marque")

    fig_pct = px.bar(
        brand_summary,
        x="marque",
        y="marge_moyenne_pct",
        text="marge_moyenne_pct",
        title="Marge moyenne % par marque"
    )

    fig_pct.update_traces(
        texttemplate="%{text:.1f} %",
        textposition="outside"
    )

    fig_pct.update_layout(
        height=420,
        xaxis_title="Marque",
        yaxis_title="Marge %",
        plot_bgcolor="white",
        paper_bgcolor="white"
    )

    st.plotly_chart(fig_pct, use_container_width=True)

with col_b:
    st.subheader("🧩 Répartition articles par marque")

    fig_count = px.pie(
        brand_summary,
        names="marque",
        values="nb_articles",
        title="Nombre d’articles analysés"
    )

    fig_count.update_layout(
        height=420,
        paper_bgcolor="white"
    )

    st.plotly_chart(fig_count, use_container_width=True)


# ============================================================
# DIMENSION SUMMARY
# ============================================================

st.subheader("🛞 Marge moyenne par dimension")

dim_summary = (
    df_filtered
    .groupby("dimension_base", as_index=False)
    .agg(
        marge_moyenne_eur=("marge_eur", "mean"),
        marge_moyenne_pct=("marge_pct", "mean"),
        poids_marche_pct=("poids_marche_pct", "max"),
        nb_articles=("article", "count")
    )
    .sort_values("poids_marche_pct", ascending=False)
)

fig_dim = px.bar(
    dim_summary.head(30),
    x="dimension_base",
    y="marge_moyenne_eur",
    text="marge_moyenne_eur",
    title="Marge € moyenne sur les dimensions du mix marché"
)

fig_dim.update_traces(
    texttemplate="%{text:.2f} €",
    textposition="outside"
)

fig_dim.update_layout(
    height=520,
    xaxis_title="Dimension",
    yaxis_title="Marge moyenne €",
    plot_bgcolor="white",
    paper_bgcolor="white"
)

st.plotly_chart(fig_dim, use_container_width=True)


# ============================================================
# ALERTS
# ============================================================

st.subheader("🚨 Alertes marge")

alerts = df_filtered[df_filtered["alerte"] != "🟢 OK"].copy()

if alerts.empty:
    st.success("Aucune alerte marge détectée.")
else:
    st.dataframe(
        alerts[
            [
                "marque",
                "article",
                "profil",
                "dimension",
                "segment",
                "bf",
                "prix_achat_net",
                "prix_vente",
                "marge_eur",
                "marge_pct",
                "alerte"
            ]
        ],
        use_container_width=True
    )


# ============================================================
# DETAILED TABLE
# ============================================================

st.subheader("📋 Détail articles")

display_cols = [
    "marque",
    "article",
    "profil",
    "dimension",
    "dimension_base",
    "segment",
    "bf",
    "remise_achat_pct",
    "prix_achat_net",
    "remise_vente_bf_pct",
    "prix_vente",
    "marge_eur",
    "marge_pct",
    "poids_marche_pct",
    "alerte"
]

st.dataframe(
    df_filtered[display_cols].sort_values(["marque", "dimension_base"]),
    use_container_width=True
)


# ============================================================
# EXPORT
# ============================================================

csv = df_filtered[display_cols].to_csv(index=False, sep=";").encode("utf-8-sig")

st.download_button(
    label="📤 Exporter les résultats CSV",
    data=csv,
    file_name="pricing_cockpit_resultats.csv",
    mime="text/csv"
)
