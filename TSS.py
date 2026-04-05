import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Animateurs", layout="wide")

# -----------------------------
# INIT SESSION
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_code_vendeur" not in st.session_state:
    st.session_state.user_code_vendeur = ""
if "commande_submitted" not in st.session_state:
    st.session_state.commande_submitted = False

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

SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Fonctions
# -----------------------------
@st.cache_data(ttl=60)
def load_sheet_df_cached(sheet_name):
    return load_sheet_df(sheet_name)

def load_sheet_df(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records()
        df = pd.DataFrame(records)

        if df.empty:
            return df

        df.columns = df.columns.str.strip()
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

        return df

    except Exception as e:
        st.warning(f"Erreur chargement '{sheet_name}' : {e}")
        return pd.DataFrame()

def append_row(sheet_name, row_values):
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet_name)
    ws.append_row(row_values)

# -----------------------------
# LOGIN
# -----------------------------
st.sidebar.header("Connexion Animateur")

if not st.session_state.logged_in:
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")

    if st.sidebar.button("Se connecter"):
        df_users = load_sheet_df_cached(SHEET_USERS)

        if df_users.empty:
            st.sidebar.error("Feuille Utilisateurs vide.")
        else:
            df_users['Email'] = df_users['Email'].astype(str).str.strip().str.lower()
            user_row = df_users[df_users['Email'] == email_input.strip().lower()]

            if user_row.empty:
                st.sidebar.error("Email non reconnu.")
            else:
                user = user_row.iloc[0]

                if str(user['Password']).strip() != password_input.strip():
                    st.sidebar.error("Mot de passe incorrect.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_email = user.get('Email', '')
                    st.session_state.user_name = user.get('Nom', 'Animateur')
                    st.session_state.user_code_vendeur = str(user.get('Code_Vendeur', '')).strip()

                    st.rerun()

# -----------------------------
# LOGOUT
# -----------------------------
if st.session_state.logged_in:
    if st.sidebar.button("Se déconnecter"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# -----------------------------
# INTERFACE
# -----------------------------
if st.session_state.logged_in:

    st.header(f"📊 TSS - Animateurs — {st.session_state.user_name}")

    df_produits = load_sheet_df_cached(SHEET_PRODUITS)
    df_list_pos = load_sheet_df_cached(SHEET_LIST_POS)

    produits_dispo = []
    for col in ['Nom Produit', 'NomProduit', 'Produit', 'Name']:
        if col in df_produits.columns:
            produits_dispo = df_produits[col].dropna().tolist()
            break

    today = datetime.now().strftime('%Y-%m-%d')

    if 'Date_Visite' in df_list_pos.columns:
        df_list_pos['Date_Visite'] = pd.to_datetime(
            df_list_pos['Date_Visite'], errors='coerce'
        ).dt.strftime('%Y-%m-%d')

        df_list_pos['Animateur'] = df_list_pos['Animateur'].astype(str).str.strip()

        df_pos_today = df_list_pos[
            (df_list_pos['Date_Visite'] == today) &
            (df_list_pos['Animateur'] == st.session_state.user_code_vendeur)
        ]
    else:
        df_pos_today = pd.DataFrame()

    tabs = st.tabs(["POS du jour", "Saisie commande", "Historique commandes"])

    # POS
    with tabs[0]:
        st.subheader("Plan de visite du jour")

        if df_pos_today.empty:
            st.info("Aucun POS aujourd'hui.")
        else:
            st.dataframe(df_pos_today, use_container_width=True)

    # Commande
    with tabs[1]:
        st.subheader("Saisie commande")

        if df_pos_today.empty:
            st.info("Aucun POS disponible.")
        else:
            code_pos = st.selectbox("POS", df_pos_today['Code_POS'].tolist())
            nom = st.text_input("Nom client *")
            prenom = st.text_input("Prénom client *")
            tel = st.text_input("Téléphone *")
            produit = st.selectbox("Produit", produits_dispo) if produits_dispo else st.text_input("Produit")
            qte = st.number_input("Quantité", min_value=1, value=1)

            if st.button("Ajouter commande"):
                if nom and prenom and tel:
                    cmd_id = str(uuid.uuid4())

                    row = [
                        cmd_id,
                        str(datetime.now()),
                        code_pos,
                        nom,
                        prenom,
                        tel,
                        produit,
                        int(qte),
                        st.session_state.user_code_vendeur,
                        "En attente"
                    ]

                    append_row(SHEET_COMMANDES, row)

                    st.success("Commande ajoutée")
                    st.session_state.commande_submitted = True
                    st.rerun()
                else:
                    st.error("Champs obligatoires manquants")

    # Historique
    with tabs[2]:
        st.subheader("Historique commandes")

        df_cmd = load_sheet_df_cached(SHEET_COMMANDES)

        if df_cmd.empty:
            st.info("Aucune commande.")
        else:
            if 'Code_Vendeur' in df_cmd.columns:

                df_cmd['Code_Vendeur'] = df_cmd['Code_Vendeur'].astype(str).str.strip().str.lower()
                user_code = st.session_state.user_code_vendeur.strip().lower()

                df_user_cmd = df_cmd[df_cmd['Code_Vendeur'] == user_code]

                if df_user_cmd.empty:
                    st.info("Aucune commande trouvée.")
                else:
                    df_user_cmd = df_user_cmd.sort_values(by=df_user_cmd.columns[1], ascending=False)
                    st.dataframe(df_user_cmd, use_container_width=True)