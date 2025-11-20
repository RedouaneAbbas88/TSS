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
# Feuilles
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
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.sidebar.header("Connexion")
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        if df_users.empty:
            st.sidebar.error("La feuille 'Utilisateurs' est vide.")
        else:
            user_row = df_users[df_users['Email'] == email_input]
            if user_row.empty:
                st.sidebar.error("Email non reconnu.")
            else:
                user_row = user_row.iloc[0]
                hashed_password = hashlib.sha256(password_input.encode()).hexdigest()
                if user_row['Password'] != hashed_password:
                    st.sidebar.error("Mot de passe incorrect.")
                else:
                    # Authentification réussie
                    st.session_state.logged_in = True
                    st.session_state.user_email = email_input
                    st.session_state.user_name = user_row.get('Nom', 'Utilisateur')
                    st.session_state.user_role = user_row.get('Role', 'PreVendeur')
                    st.session_state.user_code_vendeur = user_row.get('Code_Vendeur', '')
                    st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")

# -----------------------------
# Après login
# -----------------------------
if st.session_state.logged_in:
    user_role = st.session_state.user_role

    # -----------------------------
    # Stock Distributeur
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
    # Interface ADV
    # -----------------------------
    if user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")

        tabs = ["Ajouter Stock", "Stock Distributeur", "Commandes à valider", "État des ventes"]
        tab_choice = st.radio("Onglets ADV", tabs)

        # Ajouter Stock
        if tab_choice == "Ajouter Stock":
            st.subheader("Ajouter du stock distributeur")
            with st.form("form_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo)
                prix_achat = float(df_produits.loc[df_produits['Nom Produit'] == produit_stock, 'Prix unitaire'].values[0]) if not df_produits.empty else 0.0
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1)
                if st.form_submit_button("Ajouter au stock"):
                    row = [str(datetime.now()), produit_stock, quantite_stock, prix_achat]
                    append_row(SHEET_STOCK_DIST, row)
                    st.success(f"{quantite_stock} {produit_stock} ajouté(s) au stock.")

        # Stock Distributeur
        elif tab_choice == "Stock Distributeur":
            st.subheader("État du stock distributeur")
            df_stock = compute_stock_distributeur()
            st.dataframe(df_stock, use_container_width=True)

        # Commandes à valider
        elif tab_choice == "Commandes à valider":
            st.subheader("Commandes POS en attente de validation")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_en_attente = df_cmd[df_cmd['Statut'] == "En attente"]
            if not df_en_attente.empty:
                st.dataframe(df_en_attente[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur']], use_container_width=True)
                cmd_ids = df_en_attente['ID'].tolist()
                if "cmd_selection" not in st.session_state:
                    st.session_state.cmd_selection = cmd_ids[0]
                cmd_sel = st.selectbox("Sélectionner commande à valider", cmd_ids, index=0)
                st.session_state.cmd_selection = cmd_sel

                if st.button("Valider la commande"):
                    cmd_row_index = find_row_index(SHEET_COMMANDES, 'ID', st.session_state.cmd_selection)
                    if cmd_row_index:
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Statut', 'Validée')
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Date_validation', str(datetime.now()))
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Valide_par', st.session_state.user_email)
                        st.success("Commande validée !")
                        # Rafraîchir DataFrame
                        df_en_attente = load_sheet_df(SHEET_COMMANDES)
                        df_en_attente = df_en_attente[df_en_attente['Statut'] == "En attente"]
            else:
                st.info("Aucune commande en attente.")

        # État des ventes
        elif tab_choice == "État des ventes":
            st.subheader("État des ventes validées")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_validées = df_cmd[df_cmd['Statut'] == "Validée"]
            if not df_validées.empty:
                st.dataframe(df_validées[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.info("Aucune commande validée.")

    # -----------------------------
    # Interface Prévendeur
    # -----------------------------
    elif user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")

        tabs = ["Plan de visite", "Prise de commande", "Historique"]
        tab_choice = st.radio("Onglets Prévendeur", tabs)

        if tab_choice == "Plan de visite":
            st.subheader("Plan de visite du jour")
            today_str = datetime.now().strftime('%Y-%m-%d')
            df_plan = df_list_pos[df_list_pos['Date_Visite'] == today_str]
            if not df_plan.empty:
                st.dataframe(df_plan[['Code_POS','Nom_POS','Adresse','Wilaya']], use_container_width=True)
            else:
                st.info("Aucun POS prévu aujourd'hui.")

        elif tab_choice == "Prise de commande":
            st.subheader("Saisir une commande POS")
            with st.form("form_commande"):
                code_pos = st.text_input("Code POS")
                produit = st.selectbox("Produit", produits_dispo)
                quantite = st.number_input("Quantité", min_value=1, step=1)
                if st.form_submit_button("Enregistrer commande"):
                    row = [str(uuid.uuid4()), str(datetime.now()), code_pos, produit, quantite, st.session_state.user_code_vendeur, "En attente", "", ""]
                    append_row(SHEET_COMMANDES, row)
                    st.success("Commande enregistrée !")

        elif tab_choice == "Historique":
            st.subheader("Historique des commandes")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_cmd_user = df_cmd[df_cmd['Code_Vendeur'] == st.session_state.user_code_vendeur]
            if not df_cmd_user.empty:
                st.dataframe(df_cmd_user[['ID','Date_commande','Code_POS','Produit','Quantite','Statut']], use_container_width=True)
            else:
                st.info("Aucune commande enregistrée.")

