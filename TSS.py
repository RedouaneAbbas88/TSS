import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="TSS Distribution", layout="wide")

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
SHEET_POS = "ListofPOS"
SHEET_PRODUITS = "Produits"

# -----------------------------
# LOAD DATA
# -----------------------------
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

def append_row(sheet, row):
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet)
    ws.append_row(row)

# -----------------------------
# LOGIN
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

st.sidebar.title("Connexion")

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
                st.session_state.user_code = user["Code_Vendeur"]
                st.session_state.user_name = user["Nom"]
                st.rerun()

# -----------------------------
# APP
# -----------------------------
if st.session_state.logged_in:

    st.title(f"📊 TSS Distribution - {st.session_state.user_name}")

    df_ventes = load_sheet(SHEET_VENTES)
    df_pos = load_sheet(SHEET_POS)
    df_produits = load_sheet(SHEET_PRODUITS)

    # -----------------------------
    # SAFE CLEAN VENTES
    # -----------------------------
    if not df_ventes.empty:
        df_ventes.columns = df_ventes.columns.str.strip()

        if "qte" not in df_ventes.columns:
            st.error("Colonne 'qte' introuvable dans Ventes")
            st.stop()

        df_ventes["qte"] = pd.to_numeric(df_ventes["qte"], errors="coerce").fillna(0)

        if "Date" in df_ventes.columns:
            df_ventes["Date"] = pd.to_datetime(df_ventes["Date"], errors="coerce")

    # -----------------------------
    # POS ROUTING
    # -----------------------------
    today = pd.to_datetime(datetime.now().date())
    pos_du_jour = []

    if not df_pos.empty:
        df_pos["Date_Visite"] = pd.to_datetime(df_pos["Date_Visite"], errors="coerce")
        pos_du_jour = df_pos[df_pos["Date_Visite"].dt.date == today.date()]["Code_POS"].tolist()

    # -----------------------------
    # VENDEUR
    # -----------------------------
    if st.session_state.role == "vendeur":

        st.header("🛒 Saisie ventes")

        if not pos_du_jour:
            st.warning("Aucun POS planifié aujourd'hui")
        else:

            code_pos = st.selectbox("🏪 POS du jour", pos_du_jour)

            nom_client = st.text_input("Client (optionnel)")
            tel = st.text_input("Téléphone (optionnel)")

            familles = []
            produits_map = {}

            if not df_produits.empty:
                if "Famille" in df_produits.columns:
                    familles = df_produits["Famille"].dropna().unique().tolist()

                    for f in familles:
                        produits_map[f] = df_produits[df_produits["Famille"] == f]["Nom Produit"].tolist()

            if "lines" not in st.session_state:
                st.session_state.lines = []

            if st.button("➕ Ajouter produit"):
                st.session_state.lines.append({"famille": "", "produit": "", "qte": 1})

            new_lines = []

            for i, l in enumerate(st.session_state.lines):

                c1, c2, c3 = st.columns([2, 3, 2])

                with c1:
                    famille = st.selectbox("Famille", familles, key=f"f{i}")

                with c2:
                    produit = st.selectbox(
                        "Produit",
                        produits_map.get(famille, []),
                        key=f"p{i}"
                    )

                with c3:
                    qte = st.number_input("Qté", min_value=1, value=1, key=f"q{i}")

                new_lines.append({
                    "famille": famille,
                    "produit": produit,
                    "qte": qte
                })

            st.session_state.lines = new_lines

            if new_lines:
                st.dataframe(pd.DataFrame(new_lines))

            if st.button("💾 Enregistrer"):

                for l in new_lines:
                    row = [
                        str(uuid.uuid4()),
                        str(datetime.now()),
                        st.session_state.user_code,
                        code_pos,
                        nom_client,
                        tel,
                        l["famille"],
                        l["produit"],
                        l["qte"]
                    ]
                    append_row(SHEET_VENTES, row)

                st.success("Ventes enregistrées")
                st.session_state.lines = []

        # -----------------------------
        # MES VENTES
        # -----------------------------
        st.subheader("📜 Mes ventes")

        if not df_ventes.empty:
            my = df_ventes[df_ventes["Code_Vendeur"] == st.session_state.user_code]
            st.dataframe(my)

    # -----------------------------
    # ADMIN DASHBOARD
    # -----------------------------
    if st.session_state.role == "admin":

        st.header("📊 Dashboard Admin")

        if df_ventes.empty:
            st.warning("Aucune donnée")
            st.stop()

        df = df_ventes.copy()

        # KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("Total unités", int(df["qte"].sum()))
        c2.metric("Nb ventes", len(df))
        c3.metric("Vendeurs", df["Code_Vendeur"].nunique())

        # -----------------------------
        # PAR FAMILLE
        # -----------------------------
        st.subheader("🏷️ Par famille")

        fam = df.groupby("Famille")["qte"].sum().reset_index()
        st.dataframe(fam)
        st.bar_chart(fam.set_index("Famille"))

        # -----------------------------
        # PAR PRODUIT
        # -----------------------------
        st.subheader("📦 Produits")

        prod = df.groupby("Produit")["qte"].sum().reset_index()
        st.dataframe(prod)

        # -----------------------------
        # PAR POS
        # -----------------------------
        st.subheader("🏪 Performance POS")

        pos = df.groupby("Code_POS")["qte"].sum().reset_index()
        st.dataframe(pos)
        st.bar_chart(pos.set_index("Code_POS"))

        # -----------------------------
        # FAMILLE x POS
        # -----------------------------
        st.subheader("📊 Famille par POS")

        pivot = df.pivot_table(
            index="Code_POS",
            columns="Famille",
            values="qte",
            aggfunc="sum",
            fill_value=0
        )

        st.dataframe(pivot)

        # -----------------------------
        # VENDEURS
        # -----------------------------
        st.subheader("👤 Vendeurs")

        st.bar_chart(df.groupby("Code_Vendeur")["qte"].sum())

        # -----------------------------
        # EVOLUTION
        # -----------------------------
        st.subheader("📈 Evolution")

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        st.line_chart(df.groupby(df["Date"].dt.date)["qte"].sum())

        # -----------------------------
        # DETAIL
        # -----------------------------
        st.subheader("📜 Détail")

        st.dataframe(df)
