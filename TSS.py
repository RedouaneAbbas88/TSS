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
# Authentification simple
# -----------------------------
st.sidebar.header("Connexion")
if df_users.empty:
    st.sidebar.error("La feuille 'Utilisateurs' est vide.")
    st.stop()

user_email = st.sidebar.selectbox("Sélectionnez votre email", df_users['Email'].tolist())
user_row = df_users[df_users['Email'] == user_email].iloc[0]
user_name = user_row.get('Nom', 'Utilisateur')
user_role = user_row.get('Role', 'PreVendeur')
user_code_vendeur = user_row.get('Code_Vendeur', '')

st.sidebar.markdown(f"**{user_name}** — {user_role}")

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
    tabs = st.tabs(["📥 Ajouter stock distributeur","📋 Commandes en attente","📦 État stock distributeur"])

    # Ajouter stock distributeur
    with tabs[0]:
        st.subheader("Ajouter entrée stock distributeur")
        produit = st.selectbox("Produit", produits_dispo)
        qty = st.number_input("Quantité entrée", min_value=1, step=1, value=1)
        motif = st.text_input("Motif (ex: Achat fournisseur)")
        if st.button("Ajouter au stock"):
            today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ref = str(uuid.uuid4())
            append_row(SHEET_STOCK_DIST, [today, produit, qty, 0, '', motif, ref])
            st.success(f"+{qty} {produit} ajouté au stock.")
            compute_stock_distributeur.clear()

    # Commandes en attente
    with tabs[1]:
        st.subheader("Commandes POS — En attente")
        df_cmd = load_sheet_df(SHEET_COMMANDES)
        df_pending = df_cmd[df_cmd['Statut'] == 'En attente'] if not df_cmd.empty else pd.DataFrame()
        if df_pending.empty:
            st.info("Aucune commande en attente.")
        else:
            st.dataframe(df_pending[['ID_Commande','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur']])
            sel = st.text_input("ID_Commande à valider (copier-coller)")
            if st.button("Valider la commande sélectionnée"):
                if not sel:
                    st.error("Merci de renseigner l'ID de la commande.")
                else:
                    row_idx = find_row_index(SHEET_COMMANDES, 'ID_Commande', sel)
                    if not row_idx:
                        st.error("Commande non trouvée.")
                    else:
                        cmd = df_cmd[df_cmd['ID_Commande'] == sel].iloc[0]
                        produit = cmd['Produit']
                        quantite = int(cmd['Quantite'])
                        code_pos = cmd['Code_POS']
                        today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        ref = str(uuid.uuid4())
                        append_row(SHEET_STOCK_DIST, [today, produit, 0, quantite, code_pos, 'Livraison POS', ref])
                        update_cell(SHEET_COMMANDES, row_idx, 'Statut', 'Livré')
                        update_cell(SHEET_COMMANDES, row_idx, 'Date_validation', today)
                        update_cell(SHEET_COMMANDES, row_idx, 'Valide_par', user_email)
                        st.success(f"Commande {sel} validée et stock mis à jour.")
                        compute_stock_distributeur.clear()

    # État stock distributeur
    with tabs[2]:
        st.subheader("État du stock distributeur")
        st.dataframe(compute_stock_distributeur(), use_container_width=True)

elif user_role == 'PreVendeur':
    st.header("Espace Prévendeur — Prise de commandes POS")
    tabs = st.tabs(["📅 Plan de visite","📝 Saisir commande","📜 Historique commandes"])

    # Plan de visite
    with tabs[0]:
        st.subheader("Plan de visite du jour")
        df_pos = df_list_pos.copy()
        if not df_pos.empty and user_code_vendeur:
            today_str = datetime.now().strftime('%Y-%m-%d')
            # Conversion sécurisée des dates
            df_pos['Date_Visite'] = pd.to_datetime(df_pos['Date_Visite'], dayfirst=True, errors='coerce')
            df_pos = df_pos.dropna(subset=['Date_Visite'])
            df_pos['Date_Visite'] = df_pos['Date_Visite'].dt.strftime('%Y-%m-%d')
            df_today = df_pos[(df_pos['Date_Visite'] == today_str) & (df_pos['Code_Vendeur'] == user_code_vendeur)]
            st.dataframe(df_today[['Code_POS','Nom_POS','Adresse','Wilaya','Date_Visite']], use_container_width=True)

    # Saisir commande
    with tabs[1]:
        st.subheader("Enregistrer une commande POS (En attente)")
        code_pos = st.selectbox("Code POS", df_list_pos['Code_POS'].unique().tolist() if not df_list_pos.empty else [])
        produit = st.selectbox("Produit", produits_dispo)
        quantite = st.number_input("Quantité", min_value=1, step=1, value=1)
        if st.button("Enregistrer la commande"):
            id_cmd = str(uuid.uuid4())
            today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            append_row(SHEET_COMMANDES, [id_cmd, today, code_pos, produit, quantite, user_code_vendeur, 'En attente', '', ''])
            st.success(f"Commande {id_cmd} enregistrée (En attente).")

    # Historique commandes
    with tabs[2]:
        st.subheader("Historique des commandes saisies")
        df_cmd = load_sheet_df(SHEET_COMMANDES)
        df_my = df_cmd[df_cmd['Code_Vendeur'] == user_code_vendeur] if not df_cmd.empty else pd.DataFrame()
        st.dataframe(df_my[['ID_Commande','Date_commande','Code_POS','Produit','Quantite','Statut']])

else:
    st.warning("Rôle non reconnu. Vérifie la feuille Utilisateurs.")
