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
# Initialisation session_state
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_code_vendeur" not in st.session_state:
    st.session_state.user_code_vendeur = ""
if "panier" not in st.session_state:
    st.session_state.panier = []

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
# Feuilles nécessaires
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Chargement initial des tables
# -----------------------------
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)
produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Authentification
# -----------------------------
if not st.session_state.logged_in:
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
        # Vérification mot de passe
        hashed_input = hashlib.sha256(password_input.encode()).hexdigest()
        if user_row['Password'] != hashed_input:
            st.sidebar.error("Mot de passe incorrect.")
            st.stop()
        st.session_state.logged_in = True
        st.session_state.user_email = email_input
        st.session_state.user_name = user_row.get('Nom','Utilisateur')
        st.session_state.user_role = user_row.get('Role','PreVendeur')
        st.session_state.user_code_vendeur = user_row.get('Code_Vendeur','')
        st.experimental_rerun()

# -----------------------------
# Après connexion
# -----------------------------
if st.session_state.logged_in:
    st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")

    # -----------------------------
    # Stock Distributeur
    # -----------------------------
    @st.cache_data(ttl=10)
    def compute_stock():
        df = load_sheet_df(SHEET_STOCK_DIST)
        if df.empty:
            return pd.DataFrame(columns=['Produit','Stock'])
        df['Quantite_entree'] = pd.to_numeric(df['Quantite_entree'].fillna(0))
        df['Quantite_sortie'] = pd.to_numeric(df['Quantite_sortie'].fillna(0))
        grp = df.groupby('Produit').agg({'Quantite_entree':'sum','Quantite_sortie':'sum'}).reset_index()
        grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
        return grp[['Produit','Stock']]

    stock_df = compute_stock()

    # -----------------------------
    # Interface selon rôle
    # -----------------------------
    if st.session_state.user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")
        adv_tab = st.tabs(["Ajouter Stock", "État Stock", "Commandes à Valider", "État des Ventes"])

        with adv_tab[0]:
            st.subheader("Ajouter du stock")
            with st.form("form_add_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo)
                prix_achat = float(df_produits.loc[df_produits['Nom Produit']==produit_stock,'Prix Achat'].values[0])
                quantite_stock = st.number_input("Quantité", min_value=1, step=1)
                if st.form_submit_button("Ajouter au stock"):
                    append_row(SHEET_STOCK_DIST, [str(datetime.now()), produit_stock, quantite_stock, prix_achat, 0])
                    st.success(f"{quantite_stock} x {produit_stock} ajouté au stock.")

        with adv_tab[1]:
            st.subheader("État du stock distributeur")
            st.dataframe(stock_df, use_container_width=True)

        with adv_tab[2]:
            st.subheader("Commandes à valider")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_en_attente = df_cmd[df_cmd['Statut']=='En attente']
            if not df_en_attente.empty:
                for idx, row in df_en_attente.iterrows():
                    st.markdown(f"**Commande {row['ID']} - POS : {row['Code_POS']}**")
                    st.dataframe(pd.DataFrame([row])[['Produit','Quantite','Code_Vendeur']])
                    if st.button(f"Valider {row['ID']}", key=row['ID']):
                        # mise à jour statut
                        update_cell(SHEET_COMMANDES, idx+2, 'Statut','Validée')  # idx+2 car gspread commence à 1 et inclut header
                        update_cell(SHEET_COMMANDES, idx+2, 'Date_validation', str(datetime.now()))
                        update_cell(SHEET_COMMANDES, idx+2, 'Valide_par', st.session_state.user_email)
                        st.success(f"Commande {row['ID']} validée.")
                        st.experimental_rerun()
            else:
                st.write("Aucune commande en attente.")

        with adv_tab[3]:
            st.subheader("État des ventes")
            df_valides = df_cmd[df_cmd['Statut']=='Validée']
            if not df_valides.empty:
                st.dataframe(df_valides[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune commande validée.")

    elif st.session_state.user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")
        pre_tab = st.tabs(["Plan de Visite", "Prise de Commande", "Historique"])
        df_plan = df_list_pos[df_list_pos['Code_Vendeur']==st.session_state.user_code_vendeur]
        today_str = datetime.today().strftime('%Y-%m-%d')
        df_plan_today = df_plan[df_plan['Date_Visite']==today_str]

        with pre_tab[0]:
            st.subheader("Plan de visite du jour")
            if not df_plan_today.empty:
                st.dataframe(df_plan_today[['Code_POS','NamePos','Adresse','Wilaya']], use_container_width=True)
            else:
                st.write("Aucun POS prévu aujourd'hui.")

        with pre_tab[1]:
            st.subheader("Saisie commande")
            produit_vente = st.selectbox("Produit vendu *", produits_dispo)
            quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1)
            code_pos = st.selectbox("POS", df_plan_today['Code_POS'] if not df_plan_today.empty else [])
            if st.button("Ajouter commande"):
                if code_pos and produit_vente and quantite_vente>0:
                    cmd_id = str(uuid.uuid4())
                    append_row(SHEET_COMMANDES,[cmd_id,str(datetime.now()),code_pos,produit_vente,quantite_vente,st.session_state.user_code_vendeur,"En attente","",""])
                    st.success(f"Commande ajoutée : {cmd_id}")
                    st.experimental_rerun()

        with pre_tab[2]:
            st.subheader("Historique des commandes")
            df_histo = load_sheet_df(SHEET_COMMANDES)
            df_histo_vendeur = df_histo[df_histo['Code_Vendeur']==st.session_state.user_code_vendeur]
            if not df_histo_vendeur.empty:
                st.dataframe(df_histo_vendeur[['ID','Date_commande','Code_POS','Produit','Quantite','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune commande enregistrée.")
