import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(page_title="TSS - Distribution", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(st.secrets["google"], scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# SHEETS
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# UTILS
# -----------------------------
@st.cache_data(ttl=60)
def load_sheet(sheet):
    try:
        ws = client.open_by_key(SPREADSHEET_ID).worksheet(sheet)
        df = pd.DataFrame(ws.get_all_records())

        if not df.empty:
            df.columns = df.columns.str.strip()
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

        return df
    except Exception as e:
        st.warning(f"Erreur chargement {sheet} : {e}")
        return pd.DataFrame()

def append_row(sheet, row):
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(sheet)
    ws.append_row(row)

def update_cell(sheet, row, col_name, value):
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(sheet)
    headers = ws.row_values(1)
    if col_name in headers:
        col_index = headers.index(col_name) + 1
        ws.update_cell(row, col_index, value)

def get_column(df, possible_names):
    for col in possible_names:
        if col in df.columns:
            return df[col]
    return pd.Series()

# -----------------------------
# SESSION
# -----------------------------
for key in ['logged', 'role', 'name', 'code_vendeur', 'code_animateur']:
    if key not in st.session_state:
        st.session_state[key] = "" if key != 'logged' else False

# -----------------------------
# LOGIN
# -----------------------------
st.sidebar.title("Connexion")

if not st.session_state.logged:
    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input("Mot de passe", type="password")

    if st.sidebar.button("Se connecter"):
        df_users = load_sheet(SHEET_USERS)

        user = df_users[
            (get_column(df_users, ["Email"]) == email) &
            (get_column(df_users, ["Password"]) == password)
        ]

        if user.empty:
            st.error("Login incorrect")
        else:
            user = user.iloc[0]
            st.session_state.logged = True
            st.session_state.role = user.get("Role", "")
            st.session_state.name = user.get("Nom", "")
            st.session_state.code_vendeur = user.get("Code_Vendeur", "")
            st.session_state.code_animateur = user.get("Code_Animateur", "")

# -----------------------------
# MAIN
# -----------------------------
if st.session_state.logged:

    st.header(f"TSS Distribution — {st.session_state.name} ({st.session_state.role})")

    df_produits = load_sheet(SHEET_PRODUITS)
    df_pos = load_sheet(SHEET_LIST_POS)
    df_cmd = load_sheet(SHEET_COMMANDES)

    produits = get_column(df_produits, ["Produit", "Nom Produit", "NomProduit", "Name"]).dropna().tolist()

    # ======================================================
    # 🔵 ANIMATEUR
    # ======================================================
    if st.session_state.role == "Animateur":

        st.subheader("Saisie des ventes clients")

        today = datetime.now().strftime('%Y-%m-%d')
        code_pos = None

        if not df_pos.empty:

            df_pos['Date_Visite'] = pd.to_datetime(
                get_column(df_pos, ["Date_Visite"]), errors='coerce'
            ).dt.strftime('%Y-%m-%d')

            df_today = df_pos[
                (get_column(df_pos, ["Code_Animateur"]).astype(str) == str(st.session_state.code_animateur)) &
                (df_pos['Date_Visite'] == today)
            ]

            if df_today.empty:
                st.error("Aucun POS prévu aujourd’hui")
            else:
                if len(df_today) > 1:
                    code_pos = st.selectbox("Choisir POS", get_column(df_today, ["Code_POS"]).tolist())
                else:
                    code_pos = get_column(df_today, ["Code_POS"]).iloc[0]
                    st.success(f"POS : {code_pos}")

        if code_pos:
            with st.form("vente_client"):

                nom = st.text_input("Nom client")
                prenom = st.text_input("Prénom client")
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

        pos_list = get_column(df_pos, ["Code_POS"]).dropna().tolist()

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

        st.subheader("Suivi des commandes")

        if df_cmd.empty:
            st.info("Aucune donnée")
        else:
            tab1, tab2 = st.tabs(["En attente", "Validées"])

            with tab1:
                pending = df_cmd[df_cmd.get("Statut") == "En attente"]
                st.dataframe(pending)

            with tab2:
                valid = df_cmd[df_cmd.get("Statut") == "Validée"]
                st.dataframe(valid)
