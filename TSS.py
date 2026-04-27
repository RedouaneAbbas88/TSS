import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

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

    st.title(f"📊 Dashboard TSS - {st.session_state.user_name}")

    df = load_sheet(SHEET_VENTES)

    # =====================================================
    # CLEAN
    # =====================================================
    if not df.empty:
        df.columns = df.columns.str.strip()
        df["qte"] = pd.to_numeric(df["qte"], errors="coerce").fillna(0)

    # =====================================================
    # VENDEUR (SAISIE + HISTORIQUE)
    # =====================================================
    if st.session_state.role == "vendeur":

        st.header("🛒 Saisie des ventes")

        with st.form("form_vente"):

            col1, col2 = st.columns(2)

            with col1:
                produit = st.text_input("Produit")
                famille = st.text_input("Famille")

            with col2:
                qte = st.number_input("Quantité", min_value=1, step=1)
                code_pos = st.text_input("Code POS (optionnel)")

            submit = st.form_submit_button("Enregistrer")

            if submit:

                if produit == "" or famille == "":
                    st.error("Produit et Famille obligatoires")
                else:
                    try:
                        sh = client.open_by_key(SPREADSHEET_ID)
                        ws = sh.worksheet(SHEET_VENTES)

                        row = [
                            str(pd.Timestamp.now()),
                            st.session_state.user_code,
                            code_pos,
                            produit,
                            famille,
                            int(qte)
                        ]

                        ws.append_row(row)

                        st.success("✅ Vente enregistrée")

                    except Exception as e:
                        st.error(f"Erreur : {e}")

        # =========================
        # HISTORIQUE VENDEUR
        # =========================
        st.subheader("📋 Mes ventes")

        if not df.empty:
            my = df[df["Code_Vendeur"] == st.session_state.user_code]
            st.dataframe(my, use_container_width=True)

    # =====================================================
    # ADMIN DASHBOARD (INCHANGÉ)
    # =====================================================
    if st.session_state.role == "admin":

        st.header("📊 Dashboard Admin")

        if df.empty:
            st.warning("Aucune donnée disponible")
            st.stop()

        # KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("Total unités", int(df["qte"].sum()))
        c2.metric("Nb ventes", len(df))
        c3.metric("Vendeurs actifs", df["Code_Vendeur"].nunique())

        # GRAPHE FAMILLE
        st.subheader("📈 Ventes par famille")

        fam = df.groupby("Famille")["qte"].sum()
        st.markdown(f"### 🔢 Total global : {int(fam.sum())}")
        st.bar_chart(fam)

        # FAMILLE × PRODUIT
        st.subheader("📦 Famille × Produit")

        df_fp = df.groupby(["Famille", "Produit"])["qte"].sum().reset_index()

        rows = []
        for fam_name in df_fp["Famille"].unique():
            df_fam = df_fp[df_fp["Famille"] == fam_name]

            for _, r in df_fam.iterrows():
                rows.append({
                    "Famille": fam_name,
                    "Produit": "   ↳ " + str(r["Produit"]),
                    "Quantité": r["qte"],
                    "type": "detail"
                })

            rows.append({
                "Famille": fam_name,
                "Produit": "🔹 Sous-total",
                "Quantité": df_fam["qte"].sum(),
                "type": "total"
            })

        df_display = pd.DataFrame(rows)

        def style(row):
            if str(row.get("type", "")) == "total":
                return ["background-color:#d9edf7; font-weight:bold"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_display.drop(columns=["type"]).style.apply(style, axis=1),
            use_container_width=True
        )

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
        df_pos = df_pos.sort_values("Total Quantité", ascending=False)

        st.dataframe(df_pos, use_container_width=True)

        # VENDEUR × FAMILLE
        st.subheader("👤 Vendeur × Famille")

        df_vend = df.pivot_table(
            index="Code_Vendeur",
            columns="Famille",
            values="qte",
            aggfunc="sum",
            fill_value=0
        )

        df_vend["Total Quantité"] = df_vend.sum(axis=1)
        df_vend = df_vend.sort_values("Total Quantité", ascending=False)

        st.dataframe(df_vend, use_container_width=True)
