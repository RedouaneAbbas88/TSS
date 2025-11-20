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
# Google Sheet tables
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

    # Mot de passe en clair pour test
    if user_row['Password'] != password_input:
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
    # Interface ADV
    # -----------------------------
    if user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")

        adv_tabs = ["Ajouter Stock", "État Stock", "Commandes à valider", "État Ventes"]
        adv_choice = st.radio("Sélectionner onglet ADV", adv_tabs)

        # Onglet Ajouter Stock
        if adv_choice == "Ajouter Stock":
            st.subheader("Ajouter du stock")
            with st.form("form_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo)
                prix_achat = float(df_produits.loc[df_produits['Nom Produit']==produit_stock, 'Prix unitaire'].values[0])
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1)
                if st.form_submit_button("Ajouter au stock"):
                    row = [str(datetime.now()), produit_stock, quantite_stock, prix_achat]
                    append_row(SHEET_STOCK_DIST, row)
                    st.success(f"{quantite_stock} {produit_stock} ajouté(s) au stock.")

        # Onglet État Stock
        elif adv_choice == "État Stock":
            st.subheader("État Stock Distributeur")
            df_stock = compute_stock_distributeur()
            if not df_stock.empty:
                st.dataframe(df_stock, use_container_width=True)
            else:
                st.write("Aucun stock enregistré.")

        # Onglet Commandes à valider
        elif adv_choice == "Commandes à valider":
            st.subheader("Commandes à valider")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_cmd_en_attente = df_cmd[df_cmd['Statut'] == "En attente"]
            if df_cmd_en_attente.empty:
                st.write("Aucune commande en attente.")
            else:
                # Affichage tableau complet
                st.dataframe(df_cmd_en_attente, use_container_width=True)

                cmd_id = st.selectbox("Sélectionner commande à valider", df_cmd_en_attente['ID'])
                if st.button("Valider la commande"):
                    row_index = df_cmd_en_attente[df_cmd_en_attente['ID'] == cmd_id].index[0]
                    update_cell(SHEET_COMMANDES, row_index+2, 'Statut', "Validée")
                    update_cell(SHEET_COMMANDES, row_index+2, 'Date_validation', str(datetime.now()))
                    update_cell(SHEET_COMMANDES, row_index+2, 'Valide_par', email_input)
                    st.success("Commande validée !")

        # Onglet État Ventes
        elif adv_choice == "État Ventes":
            st.subheader("État des ventes")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            if not df_cmd.empty:
                st.dataframe(df_cmd, use_container_width=True)
            else:
                st.write("Aucune vente enregistrée.")

    # -----------------------------
    # Interface Prévendeur
    # -----------------------------
    elif user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")
        pre_tabs = ["Plan de visite", "Saisie Commande"]
        pre_choice = st.radio("Sélectionner onglet Prévendeur", pre_tabs)

        # Plan de visite
        if pre_choice == "Plan de visite":
            today = datetime.now().strftime("%Y-%m-%d")
            df_plan = df_list_pos[df_list_pos['Date_Visite']==today]
            if df_plan.empty:
                st.write("Pas de visite prévue aujourd'hui.")
            else:
                st.dataframe(df_plan[['Code_POS','Nom_POS','Adresse','Wilaya']], use_container_width=True)

        # Saisie Commande
        elif pre_choice == "Saisie Commande":
            st.subheader("Saisir une commande")
            df_plan = df_list_pos[df_list_pos['Date_Visite']==datetime.now().strftime("%Y-%m-%d"))
            if df_plan.empty:
                st.write("Pas de visite aujourd'hui.")
            else:
                pos_select = st.selectbox("Sélectionner POS", df_plan['Code_POS'])
                produit_select = st.selectbox("Produit", produits_dispo)
                quantite = st.number_input("Quantité", min_value=1, step=1)
                if st.button("Enregistrer commande"):
                    cmd_id = str(uuid.uuid4())
                    pos_data = df_plan[df_plan['Code_POS']==pos_select].iloc[0]
                    row = [
                        cmd_id,
                        str(datetime.now()),
                        pos_select,
                        produit_select,
                        quantite,
                        user_code_vendeur,
                        "En attente",
                        "",  # Date_validation
                        ""   # Valide_par
                    ]
                    append_row(SHEET_COMMANDES, row)
                    st.success("Commande enregistrée !")
