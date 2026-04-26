import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="TSS - Ventes", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = st.secrets["google"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_VENTES = "Ventes"

# -----------------------------
# FUNCTIONS
# -----------------------------
@st.cache_data(ttl=60)
def load_sheet(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

def append_row(sheet_name, row):
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet_name)
    ws.append_row(row)

# -----------------------------
# SESSION
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# -----------------------------
# LOGIN
# -----------------------------
st.sidebar.header("Connexion")

if not st.session_state.logged_in:
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Mot de passe", type="password")

    if st.sidebar.button("Se connecter"):
        df_users = load_sheet(SHEET_USERS)

        user = df_users[df_users["Email"].astype(str).str.strip() == email.strip()]

        if user.empty:
            st.sidebar.error("Email incorrect")
        else:
            user = user.iloc[0]
            if str(user["Password"]).strip() != password.strip():
                st.sidebar.error("Mot de passe incorrect")
            else:
                st.session_state.logged_in = True
                st.session_state.user_name = user.get("Nom", "User")
                st.session_state.user_code = user.get("Code_Vendeur", "")
                st.session_state.user_role = str(user.get("Role", "Vendeur")).strip().lower()
                st.success("Connecté")

# -----------------------------
# MAIN APP
# -----------------------------
if st.session_state.logged_in:

    st.title(f"📊 TSS - Ventes | {st.session_state.user_name}")

    df_produits = load_sheet(SHEET_PRODUITS)

    # -----------------------------
    # PRODUITS + FAMILLES
    # -----------------------------
    produits = []
    familles = []
    produits_par_famille = {}

    if not df_produits.empty:
        if "Nom Produit" in df_produits.columns:
            produits = df_produits["Nom Produit"].dropna().tolist()

        if "Famille" in df_produits.columns:
            familles = sorted(df_produits["Famille"].dropna().unique().tolist())

            for f in familles:
                produits_par_famille[f] = df_produits[df_produits["Famille"] == f]["Nom Produit"].tolist()

    # -----------------------------
    # SAISIE VENTES
    # -----------------------------
    st.header("🛒 Saisie des ventes")

    nom_client = st.text_input("Nom client (optionnel)")
    telephone = st.text_input("Téléphone (optionnel)")

    if "lignes" not in st.session_state:
        st.session_state.lignes = []

    if st.button("➕ Ajouter produit"):
        st.session_state.lignes.append({"famille": "", "produit": "", "quantite": 1})

    nouvelles_lignes = []
    total = 0

    for i, ligne in enumerate(st.session_state.lignes):

        col1, col2, col3, col4 = st.columns([2, 3, 2, 1])

        with col1:
            famille = st.selectbox(
                f"Famille {i+1}",
                familles,
                key=f"fam{i}"
            )

        with col2:
            produits_filtrés = produits_par_famille.get(famille, produits)
            produit = st.selectbox(
                f"Produit {i+1}",
                produits_filtrés,
                key=f"prod{i}"
            )

        with col3:
            qte = st.number_input("Qté", min_value=1, value=1, key=f"qte{i}")

        with col4:
            if st.button("❌", key=f"del{i}"):
                continue

        nouvelles_lignes.append({
            "famille": famille,
            "produit": produit,
            "quantite": qte
        })

        total += qte

    st.session_state.lignes = nouvelles_lignes

    if nouvelles_lignes:
        st.dataframe(pd.DataFrame(nouvelles_lignes), use_container_width=True)
        st.write(f"**Total produits vendus : {total}**")

    # -----------------------------
    # ENREGISTREMENT
    # -----------------------------
    if st.button("💾 Enregistrer les ventes"):
        if not nouvelles_lignes:
            st.warning("Ajoutez au moins un produit")
        else:
            for ligne in nouvelles_lignes:
                row = [
                    str(uuid.uuid4()),
                    str(datetime.now()),
                    nom_client,
                    telephone,
                    ligne["famille"],
                    ligne["produit"],
                    ligne["quantite"],
                    st.session_state.user_code
                ]
                append_row(SHEET_VENTES, row)

            st.success("✅ Ventes enregistrées")
            st.session_state.lignes = []

    # -----------------------------
    # LOAD VENTES
    # -----------------------------
    df_ventes = load_sheet(SHEET_VENTES)

    # -----------------------------
    # VENDEUR
    # -----------------------------
    if st.session_state.user_role == "vendeur":
        st.markdown("---")
        st.header("📜 Mes ventes")

        if not df_ventes.empty:
            df_user = df_ventes[
                df_ventes["Code_Vendeur"].astype(str).str.strip() == str(st.session_state.user_code).strip()
            ]

            st.dataframe(df_user.sort_values(by="Date", ascending=False), use_container_width=True)

    # -----------------------------
    # ADMIN DASHBOARD
    # -----------------------------
    if st.session_state.user_role == "admin":

        st.markdown("---")
        st.header("📊 Dashboard Admin")

        if not df_ventes.empty:

            df_ventes.columns = df_ventes.columns.str.strip()
            df_ventes["Quantite"] = pd.to_numeric(df_ventes["Quantite"], errors="coerce").fillna(0)
            df_ventes["Date"] = pd.to_datetime(df_ventes["Date"], errors="coerce")
            df_ventes = df_ventes.dropna(subset=["Date"])

            # KPI
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Produits", int(df_ventes["Quantite"].sum()))
            col2.metric("Nb Ventes", len(df_ventes))
            col3.metric("Vendeurs actifs", df_ventes["Code_Vendeur"].nunique())

            # -----------------------------
            # VENTES PAR FAMILLE
            # -----------------------------
            st.markdown("### 🏷️ Ventes par famille")

            famille_df = df_ventes.groupby("Famille")["Quantite"].sum().reset_index()
            famille_df = famille_df.sort_values(by="Quantite", ascending=False)

            st.dataframe(famille_df, use_container_width=True)
            st.bar_chart(famille_df.set_index("Famille"))

            # -----------------------------
            # DETAIL PRODUIT
            # -----------------------------
            st.markdown("### 📦 Détail par produit")

            detail_df = df_ventes.groupby(["Famille", "Produit"])["Quantite"].sum().reset_index()
            detail_df = detail_df.sort_values(by="Quantite", ascending=False)

            st.dataframe(detail_df, use_container_width=True)

            # -----------------------------
            # TOP PRODUITS
            # -----------------------------
            st.markdown("### 🏆 Top Produits")

            top_prod = df_ventes.groupby("Produit")["Quantite"].sum().sort_values(ascending=False)
            st.bar_chart(top_prod)

            # -----------------------------
            # PERFORMANCE VENDEURS
            # -----------------------------
            st.markdown("### 🧑‍💼 Performance commerciaux")

            perf = df_ventes.groupby("Code_Vendeur")["Quantite"].sum()
            st.bar_chart(perf)

            # -----------------------------
            # EVOLUTION
            # -----------------------------
            st.markdown("### 📈 Evolution")

            evo = df_ventes.groupby(df_ventes["Date"].dt.date)["Quantite"].sum()
            st.line_chart(evo)

            # -----------------------------
            # DETAIL
            # -----------------------------
            st.markdown("### 📜 Détail ventes")

            st.dataframe(df_ventes.sort_values(by="Date", ascending=False), use_container_width=True)
