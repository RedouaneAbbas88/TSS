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

# -----------------------------
# Fonctions utilitaires
# -----------------------------
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
# Noms des feuilles
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Chargement des tables
# -----------------------------
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)
df_stock = load_sheet_df(SHEET_STOCK_DIST)
df_commandes = load_sheet_df(SHEET_COMMANDES)

produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Authentification utilisateur
# -----------------------------
st.sidebar.header("Connexion")
email_input = st.sidebar.text_input("Email")
password_input = st.sidebar.text_input("Mot de passe", type="password")
login_button = st.sidebar.button("Se connecter")

if 'user_role' not in st.session_state:
    st.session_state.user_role = None

if login_button:
    user_row = df_users[df_users['Email'] == email_input]
    if user_row.empty:
        st.sidebar.error("Email non reconnu")
    else:
        user_row = user_row.iloc[0]
        if password_input != user_row['Password']:
            st.sidebar.error("Mot de passe incorrect")
        else:
            st.session_state.user_role = user_row['Role']
            st.session_state.user_name = user_row['Nom']
            st.session_state.user_code_vendeur = user_row.get('Code_Vendeur', '')
            st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")

# -----------------------------
# Vérification connexion
# -----------------------------
if st.session_state.user_role is None:
    st.stop()

# -----------------------------
# ADV Interface
# -----------------------------
if st.session_state.user_role == 'ADV':
    st.header("Espace ADV — Gestion stock & commandes")

    adv_tabs = ["Ajouter Stock", "État Stock", "Commandes à valider", "État Ventes"]
    adv_choice = st.radio("Onglet", adv_tabs)

    # Ajouter Stock
    if adv_choice == "Ajouter Stock":
        st.subheader("Ajouter du stock")
        with st.form("form_stock"):
            produit_stock = st.selectbox("Produit *", produits_dispo)
            if not df_produits.empty:
                prix_achat = float(df_produits.loc[df_produits['Nom Produit']==produit_stock, 'Prix unitaire'].values[0])
            else:
                prix_achat = 0.0
            quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1)
            submit_stock = st.form_submit_button("Ajouter au stock")
            if submit_stock:
                row = [str(datetime.now()), produit_stock, quantite_stock, prix_achat]
                append_row(SHEET_STOCK_DIST, row)
                st.success(f"{quantite_stock} x {produit_stock} ajouté(s) au stock")

    # État Stock
    elif adv_choice == "État Stock":
        st.subheader("État du stock")
        df_stock = load_sheet_df(SHEET_STOCK_DIST)
        if not df_stock.empty:
            df_stock['Quantite_entree'] = pd.to_numeric(df_stock['Quantite_entree'].fillna(0))
            df_stock['Quantite_sortie'] = pd.to_numeric(df_stock['Quantite_sortie'].fillna(0))
            stock_calc = df_stock.groupby('Produit').agg({'Quantite_entree':'sum','Quantite_sortie':'sum'}).reset_index()
            stock_calc['Stock'] = stock_calc['Quantite_entree'] - stock_calc['Quantite_sortie']
            st.dataframe(stock_calc[['Produit','Stock']], use_container_width=True)
        else:
            st.write("Aucun stock enregistré.")

    # Commandes à valider
    elif adv_choice == "Commandes à valider":
        st.subheader("Commandes à valider")
        df_commandes = load_sheet_df(SHEET_COMMANDES)
        df_attente = df_commandes[df_commandes['Statut']=="En attente"]
        if df_attente.empty:
            st.info("Aucune commande en attente")
        else:
            st.dataframe(df_attente[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur']], use_container_width=True)
            with st.form("form_valider_commande"):
                cmd_id = st.selectbox("Sélectionner commande à valider", df_attente['ID'])
                submit_valide = st.form_submit_button("Valider la commande")
                if submit_valide:
                    row_index = df_commandes.index[df_commandes['ID']==cmd_id][0] + 2  # +2 pour gspread
                    update_cell(SHEET_COMMANDES, row_index, 'Statut', 'Validée')
                    update_cell(SHEET_COMMANDES, row_index, 'Date_validation', str(datetime.now()))
                    update_cell(SHEET_COMMANDES, row_index, 'Valide_par', st.session_state.user_name)
                    st.success("Commande validée avec succès")
                    st.experimental_rerun()

    # État Ventes
    elif adv_choice == "État Ventes":
        st.subheader("État des ventes")
        df_commandes = load_sheet_df(SHEET_COMMANDES)
        if not df_commandes.empty:
            st.dataframe(df_commandes, use_container_width=True)
        else:
            st.write("Aucune commande enregistrée.")

# -----------------------------
# Prévendeur Interface
# -----------------------------
elif st.session_state.user_role == 'PreVendeur':
    st.header("Espace Prévendeur — Prise de commandes POS")

    pre_tabs = ["Plan de visite", "Saisie commande", "Historique commandes"]
    pre_choice = st.radio("Onglet", pre_tabs, horizontal=True)

    # Filtrer plan de visite du jour
    df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], format="%d/%m/%y").dt.strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    df_today = df_list_pos[(df_list_pos['Code_Vendeur']==st.session_state.user_code_vendeur) & (df_list_pos['Date_Visite']==today_str)]

    if pre_choice == "Plan de visite":
        st.subheader("Plan de visite du jour")
        if df_today.empty:
            st.write("Aucun POS à visiter aujourd'hui")
        else:
            st.dataframe(df_today[['Code_POS','Nom_POS','Adresse','Wilaya']], use_container_width=True)

    elif pre_choice == "Saisie commande":
        st.subheader("Saisie d'une commande")
        with st.form("form_commande"):
            if df_today.empty:
                st.info("Pas de POS prévu aujourd'hui")
            else:
                code_pos = st.selectbox("Sélectionner POS", df_today['Code_POS'])
                produit = st.selectbox("Produit", produits_dispo)
                quantite = st.number_input("Quantité", min_value=1, step=1)
                submit_commande = st.form_submit_button("Enregistrer la commande")
                if submit_commande:
                    row = [str(uuid.uuid4()), str(datetime.now()), code_pos, produit, quantite,
                           st.session_state.user_code_vendeur, "En attente","",""]
                    append_row(SHEET_COMMANDES, row)
                    st.success("Commande enregistrée")
                    st.experimental_rerun()

    elif pre_choice == "Historique commandes":
        st.subheader("Historique des commandes")
        df_commandes = load_sheet_df(SHEET_COMMANDES)
        df_user = df_commandes[df_commandes['Code_Vendeur']==st.session_state.user_code_vendeur]
        if df_user.empty:
            st.write("Aucune commande enregistrée")
        else:
            st.dataframe(df_user, use_container_width=True)
