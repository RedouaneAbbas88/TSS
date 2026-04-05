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
# Login
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
                    st.session_state.user_name = user.get('Nom', user.get('Name', 'Animateur'))
                    st.session_state.user_code_vendeur = user.get('Code_Vendeur', '')
                    st.sidebar.success(f"Connecté : {st.session_state.user_name}")

# -----------------------------
# Interface principale
# -----------------------------
if st.session_state.logged_in:
    st.header(f"📊 TSS - Animateurs — {st.session_state.user_name}")

    df_produits = load_sheet_df_cached(SHEET_PRODUITS)
    df_list_pos = load_sheet_df_cached(SHEET_LIST_POS)

    produits_dispo = []
    for col_name in ('Nom Produit', 'NomProduit', 'Produit', 'Name'):
        if col_name in df_produits.columns:
            produits_dispo = df_produits[col_name].dropna().tolist()
            break

    today = datetime.now().strftime('%Y-%m-%d')
    if 'Date_Visite' in df_list_pos.columns:
        df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], errors='coerce').dt.strftime('%Y-%m-%d')
        # Filtrer POS assignés à l'animateur pour aujourd'hui
        if 'Animateur' in df_list_pos.columns:
            df_pos_today = df_list_pos[
                (df_list_pos['Date_Visite'] == today) &
                (df_list_pos['Animateur'].astype(str).str.strip() == st.session_state.user_code_vendeur.strip())
            ]
        else:
            df_pos_today = df_list_pos[df_list_pos['Date_Visite'] == today]
    else:
        df_pos_today = pd.DataFrame()

    tabs = st.tabs(["POS du jour", "Saisie commande", "Historique commandes"])

    # -----------------------------
    # POS du jour
    # -----------------------------
    with tabs[0]:
        st.subheader("Plan de visite du jour")
        if df_pos_today.empty:
            st.info("Aucun POS à visiter aujourd'hui.")
        else:
            st.dataframe(df_pos_today[['Code_POS', 'Nom_POS', 'Adresse', 'Wilaya']], use_container_width=True)

    # -----------------------------
    # Saisie commande
    # -----------------------------
    with tabs[1]:
        st.subheader("Saisie d'une commande client")
        if df_pos_today.empty:
            st.info("Aucun POS disponible aujourd'hui.")
        else:
            code_pos = st.selectbox("POS à commander", df_pos_today['Code_POS'].tolist())
            nom_client = st.text_input("Nom du client *")
            prenom_client = st.text_input("Prénom du client *")
            tel_client = st.text_input("Téléphone du client *")
            produit_vente = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input("Produit *")
            quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1, value=1)
            if st.button("Ajouter commande"):
                if nom_client.strip() and prenom_client.strip() and tel_client.strip():
                    cmd_id = str(uuid.uuid4())
                    row = [
                        cmd_id,
                        str(datetime.now()),
                        code_pos,
                        nom_client.strip(),
                        prenom_client.strip(),
                        tel_client.strip(),
                        str(produit_vente),
                        int(quantite_vente),
                        st.session_state.user_code_vendeur,
                        'En attente'
                    ]
                    append_row(SHEET_COMMANDES, row)
                    st.success(f"Commande ajoutée avec ID {cmd_id}")
                    st.session_state.commande_submitted = True
                else:
                    st.error("Veuillez remplir tous les champs client.")

        # Afficher dernières commandes de l'animateur
        if st.session_state.commande_submitted:
            df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
            if not df_cmd.empty and 'Code_Vendeur' in df_cmd.columns:
                df_user_cmd = df_cmd[df_cmd['Code_Vendeur'].astype(str).str.strip() == st.session_state.user_code_vendeur.strip()]
                st.dataframe(df_user_cmd.tail(10), use_container_width=True)
            st.session_state.commande_submitted = False

    # -----------------------------
    # Historique commandes
    # -----------------------------
    with tabs[2]:
        st.subheader("Historique des commandes (votre code vendeur)")
        df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
        if df_cmd.empty:
            st.info("Aucune commande enregistrée.")
        elif 'Code_Vendeur' in df_cmd.columns:
            df_user_cmd = df_cmd[df_cmd['Code_Vendeur'].astype(str).str.strip() == st.session_state.user_code_vendeur.strip()]
            if df_user_cmd.empty:
                st.info("Aucune commande pour votre code vendeur.")
            else:
                cols = ['ID', 'Date_commande', 'Code_POS', 'Nom_Client', 'Prenom_Client', 'Tel_Client', 'Produit', 'Quantite', 'Statut']
                cols = [c for c in cols if c in df_user_cmd.columns]
                st.dataframe(df_user_cmd[cols], use_container_width=True)
