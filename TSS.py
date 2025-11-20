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
        df = pd.DataFrame(data)
        df.columns = df.columns.str.strip()  # nettoyer les colonnes pour enlever les espaces invisibles
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
    headers = worksheet.row_values(1)
    headers = [h.strip() for h in headers]
    try:
        col_idx = headers.index(col_name) + 1
    except ValueError:
        return False
    worksheet.update_cell(row, col_idx, new_value)
    return True

# -----------------------------
# Feuilles Google Sheet
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Chargement des données
# -----------------------------
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)
produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Initialisation session
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = ""
    st.session_state.user_name = ""
    st.session_state.user_code_vendeur = ""

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
        else:
            user_row = df_users[df_users['Email'] == email_input]
            if user_row.empty:
                st.sidebar.error("Email non reconnu.")
            else:
                user_row = user_row.iloc[0]
                # Connexion en clair pour test
                if user_row['Password'] != password_input:
                    st.sidebar.error("Mot de passe incorrect.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_role = user_row.get('Role','PreVendeur')
                    st.session_state.user_name = user_row.get('Nom','Utilisateur')
                    st.session_state.user_code_vendeur = user_row.get('Code_Vendeur','')
                    st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")
                    st.experimental_rerun()
else:
    st.write(f"Interface après connexion : {st.session_state.user_name} — {st.session_state.user_role}")

    # -----------------------------
    # Helper: calculer stock distributeur
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
    # Espace ADV
    # -----------------------------
    if st.session_state.user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")
        adv_tabs = st.tabs(["Ajouter Stock", "État Stock", "Commandes à valider", "État des ventes"])

        # Ajouter Stock
        with adv_tabs[0]:
            st.subheader("Ajouter du stock")
            with st.form("form_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo)
                prix_achat = 0.0
                if 'Prix unitaire' in df_produits.columns:
                    prix_vals = df_produits.loc[df_produits['Nom Produit']==produit_stock, 'Prix unitaire'].values
                    if len(prix_vals) > 0:
                        prix_achat = float(prix_vals[0])
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1)
                submitted = st.form_submit_button("Ajouter au stock")
                if submitted:
                    row = [str(datetime.now()), produit_stock, quantite_stock, prix_achat]
                    append_row(SHEET_STOCK_DIST, row)
                    st.success(f"{quantite_stock} {produit_stock} ajouté(s) au stock.")

        # État Stock
        with adv_tabs[1]:
            st.subheader("État du stock")
            df_stock = compute_stock_distributeur()
            if not df_stock.empty:
                st.dataframe(df_stock, use_container_width=True)
            else:
                st.write("Aucun stock enregistré.")

        # Commandes à valider
        with adv_tabs[2]:
            st.subheader("Commandes à valider")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            if not df_cmd.empty:
                df_pending = df_cmd[df_cmd['Statut'] == 'En attente']
                if not df_pending.empty:
                    for idx, row in df_pending.iterrows():
                        st.markdown(f"**Commande ID : {row['ID']}** — POS : {row['Code_POS']}")
                        st.dataframe(pd.DataFrame([row])[['Produit','Quantite','Code_Vendeur']], use_container_width=True)
                        if st.button(f"Valider commande {row['ID']}", key=row['ID']):
                            update_cell(SHEET_COMMANDES, idx+2, 'Statut', 'Validée')
                            update_cell(SHEET_COMMANDES, idx+2, 'Date_validation', str(datetime.now()))
                            update_cell(SHEET_COMMANDES, idx+2, 'Valide_par', st.session_state.user_name)
                            st.success(f"Commande {row['ID']} validée !")
                            st.experimental_rerun()
                else:
                    st.write("Aucune commande en attente.")
            else:
                st.write("Aucune commande enregistrée.")

        # État des ventes
        with adv_tabs[3]:
            st.subheader("État des ventes validées")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_valid = df_cmd[df_cmd['Statut'] == 'Validée']
            if not df_valid.empty:
                st.dataframe(df_valid[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune vente validée.")

    # -----------------------------
    # Espace Prévendeur
    # -----------------------------
    elif st.session_state.user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")
        pre_tabs = st.tabs(["Plan de visite", "Saisie commande", "Historique commandes"])

        # Plan de visite
        with pre_tabs[0]:
            st.subheader("Plan de visite du jour")
            df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], dayfirst=True).dt.strftime('%Y-%m-%d')
            today_str = datetime.now().strftime('%Y-%m-%d')
            df_plan = df_list_pos[df_list_pos['Date_Visite']==today_str]
            if not df_plan.empty:
                st.dataframe(df_plan[['Code_POS','Nom_POS','Adresse','Wilaya']], use_container_width=True)
            else:
                st.write("Aucun POS à visiter aujourd'hui.")

        # Saisie commande
        with pre_tabs[1]:
            st.subheader("Saisie d'une commande")
            df_pos_today = df_list_pos[df_list_pos['Date_Visite']==datetime.now().strftime('%Y-%m-%d')]
            pos_options = df_pos_today['Code_POS'].tolist() if not df_pos_today.empty else []
            code_pos = st.selectbox("POS à commander", pos_options)
            produit_vente = st.selectbox("Produit vendu *", produits_dispo)
            quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1)
            if st.button("Ajouter commande"):
                cmd_id = str(uuid.uuid4())
                row = [cmd_id, str(datetime.now()), code_pos, produit_vente, quantite_vente, st.session_state.user_code_vendeur, 'En attente', '', '']
                append_row(SHEET_COMMANDES, row)
                st.success(f"Commande ajoutée avec ID {cmd_id}")

        # Historique commandes
        with pre_tabs[2]:
            st.subheader("Historique des commandes")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_user_cmd = df_cmd[df_cmd['Code_Vendeur']==st.session_state.user_code_vendeur]
            if not df_user_cmd.empty:
                st.dataframe(df_user_cmd[['ID','Date_commande','Code_POS','Produit','Quantite','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune commande enregistrée.")
