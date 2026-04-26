import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================
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

# =====================================================
# LOAD DATA
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
                st.session_state.user_code = user["Code_Vendeur"]
                st.session_state.user_name = user["Nom"]
                st.rerun()

# =====================================================
# APP
# =====================================================
if st.session_state.logged_in:

    st.title(f"📊 TSS Distribution - {st.session_state.user_name}")

    df = load_sheet(SHEET_VENTES)

    # =====================================================
    # CLEAN DATA
    # =====================================================
    if not df.empty:
        df.columns = df.columns.str.strip()
        df["qte"] = pd.to_numeric(df["qte"], errors="coerce").fillna(0)

    # =====================================================
    # VENDEUR VIEW
    # =====================================================
    if st.session_state.role == "vendeur":

        st.header("🛒 Mes ventes")

        my = df[df["Code_Vendeur"] == st.session_state.user_code]
        st.dataframe(my)

    # =====================================================
    # ADMIN DASHBOARD
    # =====================================================
    if st.session_state.role == "admin":

        st.header("📊 Dashboard Admin")

        if df.empty:
            st.warning("Aucune donnée")
            st.stop()

        # =====================================================
        # KPI
        # =====================================================
        c1, c2, c3 = st.columns(3)
        c1.metric("Total unités", int(df["qte"].sum()))
        c2.metric("Nb lignes ventes", len(df))
        c3.metric("Vendeurs", df["Code_Vendeur"].nunique())

        # =====================================================
        # 📈 VENTES PAR FAMILLE
        # =====================================================
        st.subheader("📈 Ventes par famille")

        fam = df.groupby("Famille")["qte"].sum()

        st.markdown(f"### 🔢 Total global : {int(fam.sum())}")

        st.bar_chart(fam)

        # =====================================================
        # 📦 TABLE FAMILLE
        # =====================================================
        st.subheader("📦 Nombre de ventes par famille")

        df_fam = df.groupby("Famille").agg(
            Nombre_Ventes=("qte", "count"),
            Quantite_Totale=("qte", "sum")
        ).reset_index()

        st.dataframe(df_fam, use_container_width=True)

        # =====================================================
        # 👤 TABLE VENDEUR
        # =====================================================
        st.subheader("👤 Nombre de ventes par vendeur")

        df_vend = df.groupby("Code_Vendeur").agg(
            Nombre_Ventes=("qte", "count"),
            Quantite_Totale=("qte", "sum")
        ).reset_index()

        st.dataframe(df_vend, use_container_width=True)

        # =====================================================
        # 📦 FAMILLE × PRODUIT + SOUS-TOTAL
        # =====================================================
        st.subheader("📦 Famille × Produit (avec sous-totaux)")

        df_fp = df.groupby(["Famille", "Produit"])["qte"].sum().reset_index()

        result = []

        for fam_name in df_fp["Famille"].unique():

            df_fam = df_fp[df_fp["Famille"] == fam_name]

            for _, row in df_fam.iterrows():
                result.append({
                    "Famille": fam_name,
                    "Produit": "   ↳ " + str(row["Produit"]),
                    "Quantité": row["qte"],
                    "type": "detail"
                })

            result.append({
                "Famille": fam_name,
                "Produit": "🔹 Sous-total",
                "Quantité": df_fam["qte"].sum(),
                "type": "total"
            })

        df_display = pd.DataFrame(result)

        def highlight(row):
            if str(row.get("type", "")) == "total":
                return [
                    "background-color:#d9edf7; font-weight:bold; color:black"
                ] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_display.drop(columns=["type"]).style.apply(highlight, axis=1),
            use_container_width=True
        )

        # =====================================================
        # 🏪 POS × FAMILLE + TOTAL + NB VENTES
        # =====================================================
        st.subheader("📊 POS × Famille")

        pivot_qte = df.pivot_table(
            index="Code_POS",
            columns="Famille",
            values="qte",
            aggfunc="sum",
            fill_value=0
        )

        nb_ventes_pos = df.groupby("Code_POS")["qte"].count()

        pivot_qte["Total Quantité"] = pivot_qte.sum(axis=1)
        pivot_qte["Nb Ventes"] = nb_ventes_pos

        pivot_qte = pivot_qte.sort_values("Total Quantité", ascending=False)

        st.dataframe(pivot_qte, use_container_width=True)

        # =====================================================
        # 🏪 POS SIMPLE
        # =====================================================
        st.subheader("🏪 Ventes par POS")

        st.bar_chart(df.groupby("Code_POS")["qte"].sum())

        st.dataframe(df.groupby("Code_POS")["qte"].sum().reset_index())
