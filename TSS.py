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

        if df_users.empty:
            st.sidebar.error("Feuille utilisateurs vide")
        else:
            df_users.columns = df_users.columns.str.strip()

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

    produits = []
    if not df_produits.empty:
        for col in ["Nom Produit", "Produit", "Name"]:
            if col in df_produits.columns:
                produits = df_produits[col].dropna().tolist()
                break

    # -----------------------------
    # SAISIE VENTES (TOUT LE MONDE)
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
    # VENDEUR → SES VENTES
    # -----------------------------
    df_ventes = load_sheet(SHEET_VENTES)

    if st.session_state.user_role == "vendeur":
        st.markdown("---")
        st.header("📜 Mes ventes")

        if not df_ventes.empty:
            df_user = df_ventes[
                df_ventes["Code_Vendeur"].astype(str).str.strip() == str(st.session_state.user_code).strip()
            ]

            if df_user.empty:
                st.info("Aucune vente pour vous")
            else:
                st.dataframe(df_user.sort_values(by="Date", ascending=False), use_container_width=True)

    # -----------------------------
    # ADMIN → DASHBOARD
    # -----------------------------
    if st.session_state.user_role == "admin":

        st.markdown("---")
        st.header("📊 Dashboard Admin")

        if df_ventes.empty:
            st.warning("Aucune donnée dans Ventes")
        else:
            df_ventes.columns = df_ventes.columns.str.strip()

            if "Quantite" not in df_ventes.columns or "Date" not in df_ventes.columns:
                st.error("Colonnes manquantes")
            else:
                df_ventes["Quantite"] = pd.to_numeric(df_ventes["Quantite"], errors="coerce").fillna(0)
                df_ventes["Date"] = pd.to_datetime(df_ventes["Date"], errors="coerce")

                df_ventes = df_ventes.dropna(subset=["Date"])

                # KPI
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Produits", int(df_ventes["Quantite"].sum()))
                col2.metric("Nb Ventes", len(df_ventes))
                col3.metric("Vendeurs actifs", df_ventes["Code_Vendeur"].nunique())

                # Top produits
                st.markdown("### 🏆 Top Produits")
                st.bar_chart(df_ventes.groupby("Produit")["Quantite"].sum().sort_values(ascending=False))

                # Vendeurs
                st.markdown("### 🧑‍💼 Performance")
                st.bar_chart(df_ventes.groupby("Code_Vendeur")["Quantite"].sum())

                # Evolution
                st.markdown("### 📈 Evolution")
                st.line_chart(df_ventes.groupby(df_ventes["Date"].dt.date)["Quantite"].sum())

                # Table
                st.markdown("### 📜 Détail")
                st.dataframe(df_ventes.sort_values(by="Date", ascending=False), use_container_width=True)
