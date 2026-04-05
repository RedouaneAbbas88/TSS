import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Distribution", layout="wide")

# -----------------------------
# Google Sheets
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = st.secrets.get("google")
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# Feuilles
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Utils
# -----------------------------
@st.cache_data(ttl=60)
def load_sheet_df(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty:
            df.columns = df.columns.str.strip()
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except:
        return pd.DataFrame()

def append_row(sheet_name, row):
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    ws.append_row(row)

def update_cell(sheet_name, row, col_name, new_value):
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)
    headers = ws.row_values(1)
    col_idx = headers.index(col_name) + 1
    ws.update_cell(row, col_idx, new_value)

def compute_stock_distributeur():
    df = load_sheet_df(SHEET_STOCK_DIST)
    if df.empty:
        return pd.DataFrame()

    col_in = [c for c in df.columns if 'entree' in c.lower()]
    col_out = [c for c in df.columns if 'sortie' in c.lower()]

    df['in'] = pd.to_numeric(df[col_in[0]]) if col_in else 0
    df['out'] = pd.to_numeric(df[col_out[0]]) if col_out else 0

    grp = df.groupby('Produit').agg({'in':'sum','out':'sum'}).reset_index()
    grp['Stock'] = grp['in'] - grp['out']
    return grp[['Produit','Stock']]

# -----------------------------
# Session
# -----------------------------
for k in ['logged','role','name','code_vendeur','code_animateur']:
    if k not in st.session_state:
        st.session_state[k] = "" if k!='logged' else False

# -----------------------------
# LOGIN
# -----------------------------
st.sidebar.title("Connexion")

if not st.session_state.logged:
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Mot de passe", type="password")

    if st.sidebar.button("Se connecter"):
        df_users = load_sheet_df(SHEET_USERS)

        user = df_users[
            (df_users["Email"] == email) &
            (df_users["Password"] == password)
        ]

        if user.empty:
            st.error("Login incorrect")
        else:
            user = user.iloc[0]
            st.session_state.logged = True
            st.session_state.role = user["Role"]
            st.session_state.name = user["Nom"]
            st.session_state.code_vendeur = user.get("Code_Vendeur","")
            st.session_state.code_animateur = user.get("Code_Animateur","")

# -----------------------------
# MAIN
# -----------------------------
if st.session_state.logged:

    st.header(f"TSS Distribution — {st.session_state.name} ({st.session_state.role})")

    df_produits = load_sheet_df(SHEET_PRODUITS)
    df_pos = load_sheet_df(SHEET_LIST_POS)
    df_cmd = load_sheet_df(SHEET_COMMANDES)

    produits = df_produits['Produit'].dropna().tolist() if not df_produits.empty else []

    # ======================================================
    # 🔵 ANIMATEUR
    # ======================================================
    if st.session_state.role == "Animateur":

        st.subheader("Saisie des ventes clients")

        today = datetime.now().strftime('%Y-%m-%d')

        code_pos = None

        if not df_pos.empty:

            df_pos['Date_Visite'] = pd.to_datetime(df_pos['Date_Visite'], errors='coerce').dt.strftime('%Y-%m-%d')

            df_today = df_pos[
                (df_pos['Code_Animateur'].astype(str) == str(st.session_state.code_animateur)) &
                (df_pos['Date_Visite'] == today)
            ]

            if df_today.empty:
                st.error("Aucun POS prévu aujourd’hui")
            else:
                if len(df_today) > 1:
                    code_pos = st.selectbox("Choisir POS", df_today['Code_POS'].tolist())
                else:
                    code_pos = df_today.iloc[0]['Code_POS']
                    st.success(f"POS : {code_pos}")

        if code_pos:
            with st.form("vente_client"):
                nom = st.text_input("Nom")
                prenom = st.text_input("Prénom")
                adresse = st.text_input("Adresse")
                tel = st.text_input("Téléphone")

                produit = st.selectbox("Produit", produits)
                qte = st.number_input("Quantité", min_value=1)

                if st.form_submit_button("Valider"):
                    row = [
                        str(uuid.uuid4()),
                        str(datetime.now()),
                        code_pos,
                        produit,
                        int(qte),
                        "",
                        "Validée",
                        str(datetime.now()),
                        st.session_state.name,
                        nom, prenom, adresse, tel,
                        "SellOut",
                        st.session_state.code_animateur,
                        st.session_state.name,
                        today
                    ]
                    append_row(SHEET_COMMANDES, row)
                    st.success("Vente enregistrée")

    # ======================================================
    # 🟢 PREVENDEUR
    # ======================================================
    elif st.session_state.role == "PreVendeur":

        st.subheader("Prise de commande")

        pos_list = df_pos['Code_POS'].dropna().tolist() if not df_pos.empty else []

        code_pos = st.selectbox("POS", pos_list)
        produit = st.selectbox("Produit", produits)
        qte = st.number_input("Quantité", min_value=1)

        if st.button("Ajouter"):
            row = [
                str(uuid.uuid4()),
                str(datetime.now()),
                code_pos,
                produit,
                int(qte),
                st.session_state.code_vendeur,
                "En attente",
                "",
                "",
                "", "", "", "",
                "Commande",
                "", "",
                ""
            ]
            append_row(SHEET_COMMANDES, row)
            st.success("Commande ajoutée")

    # ======================================================
    # 🔴 ADV
    # ======================================================
    elif st.session_state.role == "ADV":

        tabs = st.tabs(["Stock","Commandes","Ventes"])

        # STOCK
        with tabs[0]:
            df_stock = compute_stock_distributeur()
            st.dataframe(df_stock)

        # COMMANDES
        with tabs[1]:
            df_pending = df_cmd[df_cmd['Statut']=="En attente"] if not df_cmd.empty else pd.DataFrame()
            st.dataframe(df_pending)

        # VENTES
        with tabs[2]:
            df_valid = df_cmd[df_cmd['Statut']=="Validée"] if not df_cmd.empty else pd.DataFrame()
            st.dataframe(df_valid)
