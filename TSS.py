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

# -----------------------------
# Fonctions utilitaires
# -----------------------------
def load_sheet_df(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()
        # nettoyage pour éviter les espaces invisibles
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except Exception as e:
        st.error(f"Erreur chargement feuille {sheet_name}: {e}")
        return pd.DataFrame()

def append_row(sheet_name, row_values):
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(sheet_name)
    worksheet.append_row(row_values)

def update_cell(sheet_name, row, col_name, new_value):
    sh = client.open_by_key(SPREADSHEET_ID)
    worksheet = sh.worksheet(sheet_name)
    headers = [h.strip() for h in worksheet.row_values(1)]
    try:
        col_idx = headers.index(col_name) + 1
    except ValueError:
        return False
    worksheet.update_cell(row, col_idx, new_value)
    return True

def compute_stock_distributeur():
    df = load_sheet_df("Stock_Distributeur")
    if df.empty:
        return pd.DataFrame(columns=['Produit','Stock'])
    df['Quantite_entree'] = pd.to_numeric(df['Quantite_entree'].fillna(0))
    df['Quantite_sortie'] = pd.to_numeric(df['Quantite_sortie'].fillna(0))
    grp = df.groupby('Produit').agg({'Quantite_entree':'sum','Quantite_sortie':'sum'}).reset_index()
    grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
    return grp[['Produit','Stock']]

# -----------------------------
# Chargement des tables
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)

produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Authentification
# -----------------------------
st.sidebar.header("Connexion")
email_input = st.sidebar.text_input("Email")
password_input = st.sidebar.text_input("Mot de passe", type="password")

if st.sidebar.button("Se connecter"):

    if df_users.empty:
        st.sidebar.error("La feuille 'Utilisateurs' est vide.")
        st.stop()

    # nettoyage espaces
    email_input_clean = email_input.strip()
    password_input_clean = password_input.strip()

    user_row = df_users[df_users['Email'].str.strip()==email_input_clean]
    if user_row.empty:
        st.sidebar.error("Email non reconnu.")
        st.stop()

    user_row = user_row.iloc[0]

    # Vérifier mot de passe
    # Option 1 : si la feuille contient le hash SHA256
    hashed_input = hashlib.sha256(password_input_clean.encode()).hexdigest()
    if 'Password' in df_users.columns and (user_row['Password']==hashed_input or user_row['Password']==password_input_clean):
        # Mot de passe correct
        st.session_state['logged_in'] = True
    else:
        st.sidebar.error("Mot de passe incorrect.")
        st.stop()

    # Infos utilisateur
    user_name = user_row.get('Nom','Utilisateur')
    user_role = user_row.get('Role','PreVendeur')
    user_code_vendeur = user_row.get('Code_Vendeur','')

    st.sidebar.success(f"Connecté : {user_name} — {user_role}")

    # Ici tu peux remettre tout ton code ADV / Prévendeur avec tabs comme dans le dernier code que je t’ai envoyé
    st.write("Interface après connexion…")
