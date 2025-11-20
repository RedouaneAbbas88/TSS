import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import hashlib

# -----------------------------
# Config Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Distribution", layout="wide")
st.title("📊 TSS - Distribution (Distributeur → POS)")

# -----------------------------
# Google Sheets / gspread
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets.get("google")
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)
SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# Fonctions
# -----------------------------
def load_sheet_df(sheet_name):
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        df = pd.DataFrame(ws.get_all_records())
        df.columns = df.columns.str.strip()
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except:
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
# Chargement données
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

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = ''
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = ''
if 'user_code_vendeur' not in st.session_state:
    st.session_state['user_code_vendeur'] = ''

if not st.session_state['logged_in']:
    if st.sidebar.button("Se connecter"):
        email_clean = email_input.strip()
        pwd_clean = password_input.strip()
        user_row = df_users[df_users['Email'].str.strip() == email_clean]
        if user_row.empty:
            st.sidebar.error("Email non reconnu.")
        else:
            user_row = user_row.iloc[0]
            hashed_input = hashlib.sha256(pwd_clean.encode()).hexdigest()
            if user_row['Password'] == hashed_input or user_row['Password'] == pwd_clean:
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = user_row['Role']
                st.session_state['user_name'] = user_row['Nom']
                st.session_state['user_code_vendeur'] = user_row.get('Code_Vendeur','')
                st.experimental_rerun()
            else:
                st.sidebar.error("Mot de passe incorrect.")
else:
    # -----------------------------
    # Interface ADV / Prévendeur
    # -----------------------------
    st.sidebar.success(f"Connecté : {st.session_state['user_name']} — {st.session_state['user_role']}")
    user_role = st.session_state['user_role']
    user_code_vendeur = st.session_state['user_code_vendeur']

    if user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")
        adv_tabs = ["Ajouter Stock","État Stock","Commandes à valider","État des ventes"]
        adv_choice = st.radio("Onglets ADV", adv_tabs, horizontal=True)

        if adv_choice == "Ajouter Stock":
            st.subheader("Ajouter du stock")
            with st.form("form_stock"):
                produit_stock = st.selectbox("Produit", produits_dispo)
                prix_achat = 0.0
                if 'Prix unitaire' in df_produits.columns:
                    vals = df_produits.loc[df_produits['Nom Produit']==produit_stock,'Prix unitaire'].values
                    if len(vals) >0:
                        prix_achat = float(vals[0])
                quantite_stock = st.number_input("Quantité", min_value=1, step=1)
                submitted = st.form_submit_button("Ajouter")
                if submitted:
                    append_row(SHEET_STOCK_DIST,[str(datetime.now()), produit_stock, quantite_stock, prix_achat])
                    st.success(f"{quantite_stock} {produit_stock} ajouté(s) au stock.")

        elif adv_choice == "État Stock":
            st.subheader("État du stock")
            df_stock = compute_stock_distributeur()
            st.dataframe(df_stock,use_container_width=True)

        elif adv_choice == "Commandes à valider":
            st.subheader("Commandes à valider")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_pending = df_cmd[df_cmd['Statut']=='En attente'] if not df_cmd.empty else pd.DataFrame()
            if not df_pending.empty:
                for idx,row in df_pending.iterrows():
                    st.markdown(f"**Commande ID : {row['ID']} — POS : {row['Code_POS']}**")
                    st.dataframe(pd.DataFrame([row])[['Produit','Quantite','Code_Vendeur']], use_container_width=True)
                    if st.button(f"Valider {row['ID']}", key=row['ID']):
                        update_cell(SHEET_COMMANDES, idx+2,'Statut','Validée')
                        update_cell(SHEET_COMMANDES, idx+2,'Date_validation',str(datetime.now()))
                        update_cell(SHEET_COMMANDES, idx+2,'Valide_par',st.session_state['user_name'])
                        st.success(f"Commande {row['ID']} validée !")
                        st.experimental_rerun()
            else:
                st.write("Aucune commande en attente.")

        elif adv_choice == "État des ventes":
            st.subheader("Ventes validées")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_valid = df_cmd[df_cmd['Statut']=='Validée'] if not df_cmd.empty else pd.DataFrame()
            if not df_valid.empty:
                st.dataframe(df_valid[['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune vente validée.")

    elif user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")
        pre_tabs = ["Plan de visite","Saisie commande","Historique commandes"]
        pre_choice = st.radio("Onglets Prévendeur", pre_tabs, horizontal=True)

        if pre_choice == "Plan de visite":
            st.subheader("Plan de visite du jour")
            df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite']).dt.strftime('%Y-%m-%d')
            today = datetime.now().strftime('%Y-%m-%d')
            df_plan = df_list_pos[df_list_pos['Date_Visite']==today]
            if not df_plan.empty:
                st.dataframe(df_plan[['Code_POS','Nom_POS','Adresse','Wilaya']],use_container_width=True)
            else:
                st.write("Aucun POS à visiter aujourd'hui.")

        elif pre_choice == "Saisie commande":
            st.subheader("Saisie commande")
            df_pos_today = df_list_pos[df_list_pos['Date_Visite']==datetime.now().strftime('%Y-%m-%d')]
            pos_options = df_pos_today['Code_POS'].tolist() if not df_pos_today.empty else []
            if pos_options:
                code_pos = st.selectbox("POS à commander", pos_options)
                produit_vente = st.selectbox("Produit vendu", produits_dispo)
                quantite_vente = st.number_input("Quantité", min_value=1, step=1)
                if st.button("Ajouter commande"):
                    cmd_id = str(uuid.uuid4())
                    append_row(SHEET_COMMANDES,[cmd_id,str(datetime.now()),code_pos,produit_vente,quantite_vente,user_code_vendeur,'En attente','',''])
                    st.success(f"Commande ajoutée: {cmd_id}")
            else:
                st.write("Aucun POS disponible aujourd'hui.")

        elif pre_choice == "Historique commandes":
            st.subheader("Historique commandes")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_user_cmd = df_cmd[df_cmd['Code_Vendeur']==user_code_vendeur] if not df_cmd.empty else pd.DataFrame()
            if not df_user_cmd.empty:
                st.dataframe(df_user_cmd[['ID','Date_commande','Code_POS','Produit','Quantite','Statut','Date_validation','Valide_par']], use_container_width=True)
            else:
                st.write("Aucune commande enregistrée.")
