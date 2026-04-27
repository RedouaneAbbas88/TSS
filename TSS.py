import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="TSS Dashboard", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["google"],
    scopes=SCOPES
)

client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

SHEET_USERS = "Utilisateurs"
SHEET_VENTES = "Ventes"
SHEET_PRODUITS = "Produits"
SHEET_POS = "ListofPOS"

# =====================================================
# LOAD
# =====================================================
def load_sheet(name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(name)
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty:
            df.columns = df.columns.str.strip()
        return df
    except:
        return pd.DataFrame()

# =====================================================
# LOGIN
# =====================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

st.sidebar.header("Connexion")

if not st.session_state.logged_in:

    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):

        users = load_sheet(SHEET_USERS)

        user = users[users["Email"].astype(str).str.strip() == email.strip()]

        if user.empty:
            st.sidebar.error("Email incorrect")
        else:
            user = user.iloc[0]

            if str(user["Password"]).strip() != password.strip():
                st.sidebar.error("Mot de passe incorrect")
            else:
                st.session_state.logged_in = True
                st.session_state.role = str(user["Role"]).lower()
                st.session_state.user_code = str(user["Code_Vendeur"]).strip()
                st.session_state.user_name = user["Nom"]
                st.rerun()

# =====================================================
# APP
# =====================================================
if st.session_state.logged_in:

    st.title(f"📊 TSS - {st.session_state.user_name}")

    df_ventes = load_sheet(SHEET_VENTES)
    df_produits = load_sheet(SHEET_PRODUITS)
    df_pos = load_sheet(SHEET_POS)

    # CLEAN
    if not df_ventes.empty:
        df_ventes["qte"] = pd.to_numeric(df_ventes["qte"], errors="coerce").fillna(0)

    # =====================================================
    # VENDEUR
    # =====================================================
    if st.session_state.role == "vendeur":

        st.header("🛒 Saisie des ventes")

        # -------------------------
        # ROUTING POS (AUJOURD’HUI)
        # -------------------------
        pos_options = []

        if not df_pos.empty:

            df_pos["Date_Visite"] = pd.to_datetime(
                df_pos["Date_Visite"], errors="coerce"
            ).dt.date

            today = datetime.now().date()

            df_today = df_pos[
                (df_pos["Code_Animateur"].astype(str).str.strip() == st.session_state.user_code)
                & (df_pos["Date_Visite"] == today)
            ]

            pos_options = df_today["Code_POS"].dropna().tolist()

        # -------------------------
        # PRODUITS
        # -------------------------
        if df_produits.empty:
            st.error("Table Produits vide")
            st.stop()

        familles = sorted(df_produits["Famille"].dropna().unique())

        with st.form("form_vente"):

            # FAMILLE
            famille = st.selectbox("Famille", familles)

            # PRODUIT FILTRÉ
            produits = df_produits[
                df_produits["Famille"] == famille
            ]["Nom Produit"].dropna().tolist()

            produit = st.selectbox("Produit", produits)

            # POS (ROUTING)
            if pos_options:
                code_pos = st.selectbox("POS (plan du jour)", pos_options)
            else:
                st.warning("⚠ Aucun POS prévu aujourd'hui")
                code_pos = st.text_input("Code POS manuel")

            col1, col2 = st.columns(2)

            with col1:
                qte = st.number_input("Quantité", min_value=1, step=1)

            with col2:
                client_nom = st.text_input("Nom Client")
                telephone = st.text_input("Téléphone")

            submit = st.form_submit_button("Enregistrer")

            if submit:

                try:
                    ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_VENTES)

                    row = [
                        str(uuid.uuid4()),
                        str(datetime.now()),
                        st.session_state.user_code,
                        code_pos,
                        client_nom,
                        telephone,
                        famille,
                        produit,
                        int(qte)
                    ]

                    ws.append_row(row)

                    st.success("✅ Vente enregistrée")

                except Exception as e:
                    st.error(f"Erreur : {e}")

        # -------------------------
        # HISTORIQUE
        # -------------------------
        st.subheader("📋 Mes ventes")

        if not df_ventes.empty:
            my = df_ventes[
                df_ventes["Code_Vendeur"].astype(str).str.strip()
                == st.session_state.user_code
            ]
            st.dataframe(my, use_container_width=True)

    # =====================================================
    # ADMIN (INCHANGÉ)
    # =====================================================
    if st.session_state.role == "admin":

        st.header("📊 Dashboard Admin")

        if df_ventes.empty:
            st.warning("Aucune donnée disponible")
            st.stop()

        df = df_ventes.copy()
        df["qte"] = pd.to_numeric(df["qte"], errors="coerce").fillna(0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total unités", int(df["qte"].sum()))
        c2.metric("Nb ventes", len(df))
        c3.metric("Vendeurs actifs", df["Code_Vendeur"].nunique())

        st.subheader("📈 Ventes par famille")
        st.bar_chart(df.groupby("Famille")["qte"].sum())

        st.subheader("📦 Famille × Produit")
        st.dataframe(df.groupby(["Famille","Produit"])["qte"].sum().reset_index())

        st.subheader("🏪 POS × Famille")
        st.dataframe(df.pivot_table(index="Code_POS", columns="Famille", values="qte", aggfunc="sum", fill_value=0))

        st.subheader("👤 Vendeur × Famille")
        st.dataframe(df.pivot_table(index="Code_Vendeur", columns="Famille", values="qte", aggfunc="sum", fill_value=0))
