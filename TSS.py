import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import hashlib

# -----------------------------
# Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Distribution", layout="wide")
st.title("📊 TSS - Distribution (Distributeur → POS)")

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

@st.cache_data(ttl=30)
def load_sheet_df(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erreur chargement feuille {sheet_name}: {e}")
        return pd.DataFrame()


def append_row(sheet_name, row_values):
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(sheet_name)
    worksheet.append_row(row_values)


def find_row_index(sheet_name, column_name, value):
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(sheet_name)
    headers = worksheet.row_values(1)
    try:
        col_idx = headers.index(column_name) + 1
    except ValueError:
        return None
    try:
        cell = worksheet.find(str(value), in_column=col_idx)
        return cell.row
    except Exception:
        return None


def update_cell(sheet_name, row, col_name, new_value):
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(sheet_name)
    headers = worksheet.row_values(1)
    try:
        col_idx = headers.index(col_name) + 1
    except ValueError:
        return False
    worksheet.update_cell(row, col_idx, new_value)
    return True

# -----------------------------
# Chargement des tables nécessaires
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# Chargements initiaux
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)

produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Authentification utilisateur
# -----------------------------
st.sidebar.header("Connexion")

email_input = st.sidebar.text_input("Email")
password_input = st.sidebar.text_input("Mot de passe", type="password")

if st.sidebar.button("Se connecter"):
    if df_users.empty:
        st.sidebar.error("La feuille 'Utilisateurs' est vide.")
        st.stop()

    user_row = df_users[df_users['Email'] == email_input]
    if user_row.empty:
        st.sidebar.error("Email non reconnu.")
        st.stop()

    user_row = user_row.iloc[0]
    # Vérifier mot de passe (hashé avec SHA256 pour exemple)
    hashed_password = hashlib.sha256(password_input.encode()).hexdigest()
    if user_row['Password'] != hashed_password:
        st.sidebar.error("Mot de passe incorrect.")
        st.stop()

    user_name = user_row.get('Nom', 'Utilisateur')
    user_role = user_row.get('Role', 'PreVendeur')
    user_code_vendeur = user_row.get('Code_Vendeur', '')

    st.sidebar.success(f"Connecté : {user_name} — {user_role}")

    # -----------------------------
    # Helper: calculer stock courant distributeur
    # -----------------------------
    @st.cache_data(ttl=10)
    def compute_stock_distributeur():
        df = load_sheet_df(SHEET_STOCK_DIST)
        if df.empty:
            return pd.DataFrame(columns=['Produit', 'Stock'])
        df['Quantite_entree'] = pd.to_numeric(df['Quantite_entree'].fillna(0))
        df['Quantite_sortie'] = pd.to_numeric(df['Quantite_sortie'].fillna(0))
        grp = df.groupby('Produit').agg({'Quantite_entree':'sum','Quantite_sortie':'sum'}).reset_index()
        grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
        return grp[['Produit','Stock']]

    # -----------------------------
    # Interface selon rôle
    # -----------------------------
    if user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")
        # ... le reste du code ADV (onglets, ajout stock, validation commandes, état stock) reste identique ...

    elif user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")
        # ... le reste du code Prévendeur (plan de visite, saisie commande, historique) reste identique ...

    else:
        st.warning("Rôle non reconnu. Vérifie la feuille Utilisateurs.")
