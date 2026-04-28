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
# LOAD FUNCTION
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
                st.session_state.role = str(user["Role"]).lower().strip()
                st.session_state.user_code = str(user["Code_Vendeur"]).strip()
                st.session_state.user_name = user["Nom"]
                st.rerun()

# =====================================================
# APP
# =====================================================
if st.session_state.logged_in:

    st.title(f"📊 365 DAYS - {st.session_state.user_name}")

    df_ventes = load_sheet(SHEET_VENTES)
    df_produits = load_sheet(SHEET_PRODUITS)
    df_pos = load_sheet(SHEET_POS)

    # CLEAN
    if not df_produits.empty:
        df_produits["Famille"] = df_produits["Famille"].astype(str).str.strip()
        df_produits["Nom Produit"] = df_produits["Nom Produit"].astype(str).str.strip()

    if not df_ventes.empty:
        df_ventes["qte"] = pd.to_numeric(df_ventes["qte"], errors="coerce").fillna(0)
        df_ventes["Famille"] = df_ventes["Famille"].astype(str).str.strip()
        df_ventes.columns = df_ventes.columns.str.strip()

    # =====================================================
    # VENDEUR
    # =====================================================
    if st.session_state.role == "vendeur":

        st.header("🛒 Saisie des ventes")

        if df_produits.empty:
            st.error("Table Produits vide")
            st.stop()

        familles = sorted(df_produits["Famille"].dropna().unique())

        if "famille_selected" not in st.session_state:
            st.session_state.famille_selected = familles[0]

        famille = st.selectbox(
            "Famille",
            familles,
            key="famille_selected"
        )

        produits = df_produits[
            df_produits["Famille"] == famille
        ]["Nom Produit"].tolist()

        if not produits:
            st.warning("Aucun produit dans cette famille")
            st.stop()

        if "produit_selected" not in st.session_state or st.session_state.produit_selected not in produits:
            st.session_state.produit_selected = produits[0]

        produit = st.selectbox(
            "Produit",
            produits,
            key="produit_selected"
        )

        pos_options = []
        if not df_pos.empty:
            df_pos["Date_Visite"] = pd.to_datetime(df_pos["Date_Visite"], errors="coerce").dt.date
            today = datetime.now().date()

            df_today = df_pos[
                (df_pos["Code_Animateur"].astype(str).str.strip() == st.session_state.user_code)
                & (df_pos["Date_Visite"] == today)
            ]

            pos_options = df_today["Code_POS"].dropna().tolist()

        with st.form("form_vente"):

            if pos_options:
                code_pos = st.selectbox("POS (plan du jour)", pos_options)
            else:
                code_pos = st.text_input("Code POS")

            col1, col2 = st.columns(2)

            with col1:
                qte = st.number_input("Quantité", min_value=1)

            with col2:
                client_nom = st.text_input("Nom Client")
                telephone = st.text_input("Téléphone")

            submit = st.form_submit_button("Enregistrer")

            if submit:

                ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_VENTES)

                ws.append_row([
                    str(uuid.uuid4()),
                    str(datetime.now()),
                    st.session_state.user_code,
                    code_pos,
                    client_nom,
                    telephone,
                    famille,
                    produit,
                    int(qte)
                ])

                st.success("✅ Vente enregistrée")

        st.subheader("📋 Mes ventes")

        if not df_ventes.empty:
            st.dataframe(df_ventes[df_ventes["Code_Vendeur"] == st.session_state.user_code])

    # =====================================================
    # ADMIN
    # =====================================================
    if st.session_state.role == "admin":

        st.header("📊 Dashboard Admin")

        if df_ventes.empty:
            st.warning("Aucune donnée disponible")
            st.stop()

        df = df_ventes.copy()

        # KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("Total unités", int(df["qte"].sum()))
        c2.metric("Nb ventes", len(df))
        c3.metric("Vendeurs actifs", df["Code_Vendeur"].nunique())

        # GRAPHE
        st.subheader("📈 Ventes par famille")
        st.bar_chart(df.groupby("Famille")["qte"].sum())

        # FAMILLE × PRODUIT
        st.subheader("📦 Famille × Produit")

        df_gp = df.groupby(["Famille", "Produit"])["qte"].sum().reset_index()

        rows = []
        total_global = 0

        for fam in df_gp["Famille"].unique():

            df_fam = df_gp[df_gp["Famille"] == fam]

            for _, r in df_fam.iterrows():
                rows.append({
                    "Famille": fam,
                    "Produit": r["Produit"],
                    "Quantité": r["qte"]
                })

            sous_total = df_fam["qte"].sum()
            total_global += sous_total

            rows.append({
                "Famille": fam,
                "Produit": "🔹 Sous-total",
                "Quantité": sous_total
            })

        rows.append({
            "Famille": "TOTAL GLOBAL",
            "Produit": "",
            "Quantité": total_global
        })

        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # POS × FAMILLE
        st.subheader("🏪 POS × Famille")

        df_pos = df.pivot_table(
            index="Code_POS",
            columns="Famille",
            values="qte",
            aggfunc="sum",
            fill_value=0
        )

        df_pos["Total Quantité"] = df_pos.sum(axis=1)

        st.dataframe(df_pos)

        # =====================================================
        # ✅ VENDEUR × FAMILLE (MODIFIÉ)
        # =====================================================
        st.subheader("👤 Vendeur × Famille")

        df_users = load_sheet(SHEET_USERS)

        if not df_users.empty:
            df_users["Code_Vendeur"] = df_users["Code_Vendeur"].astype(str).str.strip()
            df_users["Nom"] = df_users["Nom"].astype(str).str.strip()

            if "Code_Vendeur" in df.columns:
                df["Code_Vendeur"] = df["Code_Vendeur"].astype(str).str.strip()

                df_merge = df.merge(
                    df_users[["Code_Vendeur", "Nom"]],
                    on="Code_Vendeur",
                    how="left"
                )

                df_merge["Nom"] = df_merge["Nom"].fillna("Inconnu")

                df_vend = df_merge.pivot_table(
                    index="Nom",
                    columns="Famille",
                    values="qte",
                    aggfunc="sum",
                    fill_value=0
                )

                df_vend["Total Quantité"] = df_vend.sum(axis=1)

                st.dataframe(df_vend)
            else:
                st.error("Colonne Code_Vendeur introuvable dans Ventes")
