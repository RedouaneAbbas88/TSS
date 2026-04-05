import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Animateurs POS", layout="wide")

# -----------------------------
# Google Sheets / gspread
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
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Fonctions utilitaires
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
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except Exception as e:
        st.warning(f"Impossible de charger la feuille '{sheet_name}' ({e})")
        return pd.DataFrame()

def append_row(sheet_name, row_values):
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet_name)
    ws.append_row(row_values)

# -----------------------------
# Session state
# -----------------------------
for key in ['logged_in', 'user_email', 'user_name', 'user_code_vendeur', 'commande_submitted']:
    if key not in st.session_state:
        st.session_state[key] = False if 'submitted' in key or 'logged_in' in key else ''

# -----------------------------
# Login Animateur
# -----------------------------
st.sidebar.header("Connexion Animateur")
if not st.session_state.logged_in:
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        df_users = load_sheet_df_cached(SHEET_USERS)
        if df_users.empty:
            st.sidebar.error("Feuille 'Utilisateurs' vide ou introuvable.")
        else:
            mask = df_users['Email'].astype(str).str.strip() == email_input.strip()
            user_rows = df_users[mask]
            if user_rows.empty:
                st.sidebar.error("Email non reconnu.")
            else:
                user = user_rows.iloc[0]
                if str(user['Password']).strip() != password_input.strip():
                    st.sidebar.error("Mot de passe incorrect.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_email = user.get('Email', '').strip()
                    st.session_state.user_name = user.get('Nom', user.get('Name', 'Utilisateur'))
                    st.session_state.user_code_vendeur = user.get('Code_Vendeur', '')

# -----------------------------
# Interface Animateur
# -----------------------------
if st.session_state.logged_in:
    st.header(f"📊 TSS - Animateur — {st.session_state.user_name}")

    df_produits = load_sheet_df_cached(SHEET_PRODUITS)
    produits_dispo = []
    if not df_produits.empty:
        for col_name in ('Nom Produit', 'NomProduit', 'Produit', 'Name'):
            if col_name in df_produits.columns:
                produits_dispo = df_produits[col_name].dropna().tolist()
                break

    df_list_pos = load_sheet_df_cached(SHEET_LIST_POS)
    today = datetime.now().strftime('%Y-%m-%d')

    tabs = st.tabs(["Plan de visite", "Saisie commande", "Historique commandes"])

    # -----------------------------
    # Onglet Plan de visite
    # -----------------------------
    with tabs[0]:
        st.markdown("**Plan de visite du jour**")
        required_cols = ['Code_POS', 'Nom_POS', 'Adresse', 'Wilaya', 'Code_Animateur', 'Date_Visite']
        if all(col in df_list_pos.columns for col in required_cols):
            df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], errors='coerce').dt.strftime('%Y-%m-%d')
            df_today_pos = df_list_pos[
                (df_list_pos['Date_Visite'] == today) &
                (df_list_pos['Code_Animateur'].astype(str).str.strip() == str(st.session_state.user_code_vendeur).strip())
            ]
            if df_today_pos.empty:
                st.info("Aucun POS assigné pour vous aujourd'hui.")
            else:
                st.dataframe(df_today_pos[['Code_POS', 'Nom_POS', 'Adresse', 'Wilaya']], use_container_width=True)
        else:
            st.error("La table ListofPOS doit contenir : " + ", ".join(required_cols))

    # -----------------------------
    # Onglet Saisie commande
    # -----------------------------
    with tabs[1]:
        st.markdown("**Saisie d'une commande**")
        if not df_list_pos.empty:
            df_today_pos = df_list_pos[
                (df_list_pos['Date_Visite'] == today) &
                (df_list_pos['Code_Animateur'].astype(str).str.strip() == str(st.session_state.user_code_vendeur).strip())
            ]
            if df_today_pos.empty:
                st.info("Aucun POS prévu aujourd'hui.")
            else:
                for idx, pos_row in df_today_pos.iterrows():
                    st.markdown(f"### POS : {pos_row['Nom_POS']} ({pos_row['Code_POS']})")
                    with st.form(f"form_cmd_{pos_row['Code_POS']}"):
                        nom_client = st.text_input("Nom client *", key=f"nom_{pos_row['Code_POS']}")
                        prenom_client = st.text_input("Prénom client *", key=f"prenom_{pos_row['Code_POS']}")
                        adresse_client = st.text_input("Adresse client", key=f"adresse_{pos_row['Code_POS']}")
                        produit_vente = st.selectbox("Produit *", produits_dispo, key=f"prod_{pos_row['Code_POS']}")
                        quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1, value=1, key=f"qt_{pos_row['Code_POS']}")
                        submitted = st.form_submit_button("Ajouter commande", key=f"submit_{pos_row['Code_POS']}")
                        if submitted:
                            cmd_id = str(uuid.uuid4())
                            row = [cmd_id, str(datetime.now()), pos_row['Code_POS'], produit_vente, quantite_vente,
                                   st.session_state.user_code_vendeur, nom_client, prenom_client, adresse_client,
                                   'En attente', '', '']
                            append_row(SHEET_COMMANDES, row)
                            st.success(f"Commande ajoutée pour {pos_row['Nom_POS']} (ID: {cmd_id})")

    # -----------------------------
    # Onglet Historique commandes
    # -----------------------------
    with tabs[2]:
        st.markdown("**Historique des commandes (votre code vendeur)**")
        df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
        if df_cmd.empty:
            st.info("Aucune commande enregistrée.")
        elif 'Code_Vendeur' in df_cmd.columns:
            df_user_cmd = df_cmd[df_cmd['Code_Vendeur'].astype(str).str.strip() == str(st.session_state.user_code_vendeur).strip()]
            if df_user_cmd.empty:
                st.info("Aucune commande pour votre code vendeur.")
            else:
                cols = [c for c in ['ID', 'Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Nom_Client', 'Prenom_Client', 'Adresse_Client', 'Statut'] if c in df_user_cmd.columns]
                st.dataframe(df_user_cmd[cols], use_container_width=True)
