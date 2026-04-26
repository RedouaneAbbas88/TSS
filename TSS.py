import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="TSS - Ventes & Dashboard", layout="wide")

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

        if df_users.empty:
            st.sidebar.error("Feuille utilisateurs vide")
        else:
            user = df_users[df_users["Email"] == email]

            if user.empty:
                st.sidebar.error("Email incorrect")
            else:
                user = user.iloc[0]
                if str(user["Password"]) != password:
                    st.sidebar.error("Mot de passe incorrect")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_name = user.get("Nom", "User")
                    st.session_state.user_code = user.get("Code_Vendeur", "")
                    st.success("Connecté")

# -----------------------------
# MAIN APP
# -----------------------------
if st.session_state.logged_in:

    st.title(f"📊 TSS - Ventes | {st.session_state.user_name}")

    df_produits = load_sheet(SHEET_PRODUITS)

    produits = []
    if not df_produits.empty:
        for col in ["Nom Produit", "Produit", "Name"]:
            if col in df_produits.columns:
                produits = df_produits[col].dropna().tolist()
                break

    # -----------------------------
    # SAISIE VENTES
    # -----------------------------
    st.header("🛒 Saisie des ventes")

    nom_client = st.text_input("Nom client (optionnel)")
    telephone = st.text_input("Téléphone (optionnel)")

    if "lignes" not in st.session_state:
        st.session_state.lignes = []

    if st.button("➕ Ajouter produit"):
        st.session_state.lignes.append({"produit": "", "quantite": 1})

    nouvelles_lignes = []
    total = 0

    for i, ligne in enumerate(st.session_state.lignes):
        col1, col2, col3 = st.columns([3, 2, 1])

        with col1:
            produit = st.selectbox(f"Produit {i+1}", produits, key=f"p{i}")
        with col2:
            qte = st.number_input(f"Qté {i+1}", min_value=1, value=ligne["quantite"], key=f"q{i}")
        with col3:
            if st.button("❌", key=f"d{i}"):
                continue

        nouvelles_lignes.append({"produit": produit, "quantite": qte})
        total += qte

    st.session_state.lignes = nouvelles_lignes

    if nouvelles_lignes:
        st.dataframe(pd.DataFrame(nouvelles_lignes), use_container_width=True)
        st.write(f"**Total produits vendus : {total}**")

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
                    ligne["produit"],
                    ligne["quantite"],
                    st.session_state.user_code
                ]
                append_row(SHEET_VENTES, row)

            st.success("✅ Ventes enregistrées")
            st.session_state.lignes = []

    # -----------------------------
    # DASHBOARD
    # -----------------------------
    st.markdown("---")
    st.header("📊 Dashboard")

    df_ventes = load_sheet(SHEET_VENTES)

    if df_ventes.empty:
        st.warning("Aucune donnée disponible")
    else:
        df_ventes['Quantite'] = pd.to_numeric(df_ventes['Quantite'], errors='coerce').fillna(0)
        df_ventes['Date'] = pd.to_datetime(df_ventes['Date'], errors='coerce')

        # KPI
        col1, col2, col3 = st.columns(3)
        col1.metric("Total produits vendus", int(df_ventes['Quantite'].sum()))
        col2.metric("Nombre de ventes", len(df_ventes))
        col3.metric("Commerciaux actifs", df_ventes['Code_Vendeur'].nunique())

        # Filtre date
        st.markdown("### 📅 Filtre")
        date_range = st.date_input("Période", [])

        if len(date_range) == 2:
            df_ventes = df_ventes[
                (df_ventes['Date'] >= pd.to_datetime(date_range[0])) &
                (df_ventes['Date'] <= pd.to_datetime(date_range[1]))
            ]

        # Top produits
        st.markdown("### 🏆 Top Produits")
        st.bar_chart(df_ventes.groupby('Produit')['Quantite'].sum().sort_values(ascending=False))

        # Performance vendeurs
        st.markdown("### 🧑‍💼 Performance commerciaux")
        st.bar_chart(df_ventes.groupby('Code_Vendeur')['Quantite'].sum())

        # Evolution
        st.markdown("### 📈 Evolution")
        st.line_chart(df_ventes.groupby(df_ventes['Date'].dt.date)['Quantite'].sum())

        # Table
        st.markdown("### 📜 Détail")
        st.dataframe(df_ventes.sort_values(by="Date", ascending=False), use_container_width=True)
