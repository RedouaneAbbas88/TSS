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

# -----------------------------
# Google Sheets / gspread
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Credentials Streamlit secrets
creds_dict = st.secrets.get("google")
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# Fonctions utilitaires
# -----------------------------
def load_sheet_df(sheet_name):
    """Charge une feuille Google Sheet et nettoie colonnes et chaînes"""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
        df.columns = df.columns.str.strip()
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except Exception as e:
        st.warning(f"Impossible de charger la feuille '{sheet_name}' ({e})")
        return pd.DataFrame()

def append_row(sheet_name, row_values):
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet_name)
    ws.append_row(row_values)

def update_cell(sheet_name, row, col_name, new_value):
    """Met à jour une cellule par nom de colonne et numéro de ligne"""
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(sheet_name)
    headers = [h.strip() for h in ws.row_values(1)]
    try:
        col_idx = headers.index(col_name) + 1
    except ValueError:
        return False
    ws.update_cell(row, col_idx, new_value)
    return True

def compute_stock_distributeur():
    """Calcule le stock actuel par produit"""
    df = load_sheet_df("Stock_Distributeur")
    if df.empty or 'Produit' not in df.columns:
        return pd.DataFrame(columns=['Produit','Stock'])
    df['Quantite_entree'] = pd.to_numeric(df.get('Quantite_entree',0), errors='coerce').fillna(0)
    df['Quantite_sortie'] = pd.to_numeric(df.get('Quantite_sortie',0), errors='coerce').fillna(0)
    grp = df.groupby('Produit', as_index=False).agg({'Quantite_entree':'sum','Quantite_sortie':'sum'})
    grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
    return grp[['Produit','Stock']]

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
# Chargement initial des tables
# -----------------------------
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)

produits_dispo = []
if not df_produits.empty:
    for col_name in ('Nom Produit','NomProduit','Produit','Name'):
        if col_name in df_produits.columns:
            produits_dispo = df_produits[col_name].dropna().tolist()
            break

# -----------------------------
# Session state
# -----------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ''
    st.session_state.user_role = ''
    st.session_state.user_name = ''
    st.session_state.user_code_vendeur = ''
    st.session_state.stock_submitted = False
    st.session_state.commande_submitted = False
    st.session_state.command_validated = False

# -----------------------------
# Interface de connexion
# -----------------------------
st.sidebar.header("Connexion")
if not st.session_state.logged_in:
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        email_in = email_input.strip()
        pwd_in = password_input.strip()
        if df_users.empty or 'Email' not in df_users.columns:
            st.sidebar.error("Feuille 'Utilisateurs' vide ou colonne 'Email' manquante")
        else:
            user_rows = df_users[df_users['Email'].astype(str).str.strip() == email_in]
            if user_rows.empty:
                st.sidebar.error("Email non reconnu")
            else:
                user = user_rows.iloc[0]
                pw_sheet = str(user.get('Password','')).strip()
                if pw_sheet != pwd_in:
                    st.sidebar.error("Mot de passe incorrect")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_email = user.get('Email','').strip()
                    st.session_state.user_role = user.get('Role','PreVendeur')
                    st.session_state.user_name = user.get('Nom', user.get('Name','Utilisateur'))
                    st.session_state.user_code_vendeur = user.get('Code_Vendeur','')
                    st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")

# -----------------------------
# Interface principale
# -----------------------------
if st.session_state.logged_in:
    st.header(f"📊 TSS - Distribution — {st.session_state.user_name} ({st.session_state.user_role})")
    st.write("")

    # Recharger tables dynamiques
    df_produits = load_sheet_df(SHEET_PRODUITS)
    df_list_pos = load_sheet_df(SHEET_LIST_POS)
    produits_dispo = []
    if not df_produits.empty:
        for col_name in ('Nom Produit','NomProduit','Produit','Name'):
            if col_name in df_produits.columns:
                produits_dispo = df_produits[col_name].dropna().tolist()
                break

    # -----------------------------
    # Espace ADV
    # -----------------------------
    if st.session_state.user_role == 'ADV':
        st.subheader("Espace ADV — Gestion stock & validation commandes")
        tabs = st.tabs(["Ajouter Stock","État Stock","Commandes à valider","État des ventes"])

        # Ajouter Stock
        with tabs[0]:
            st.markdown("**Ajouter du stock**")
            with st.form("form_add_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input("Produit *")
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1, value=1)
                prix_achat = st.text_input("Prix unitaire (optionnel)", value="")
                submitted = st.form_submit_button("Ajouter au stock")
                if submitted:
                    prix_val = float(prix_achat) if prix_achat.strip() != "" else 0.0
                    row = [str(datetime.now()), str(produit_stock), int(quantite_stock), prix_val]
                    append_row(SHEET_STOCK_DIST, row)
                    st.success(f"{quantite_stock} x {produit_stock} ajouté(s) au stock distributeur.")
                    st.session_state.stock_submitted = True

            if st.session_state.stock_submitted:
                df_stock = compute_stock_distributeur()
                st.markdown("**Stock actuel (mis à jour)**")
                st.dataframe(df_stock, use_container_width=True)
                st.session_state.stock_submitted = False

        # État Stock
        with tabs[1]:
            st.markdown("**État du stock**")
            df_stock = compute_stock_distributeur()
            if df_stock.empty:
                st.info("Aucun stock enregistré.")
            else:
                st.dataframe(df_stock, use_container_width=True)

        # Commandes à valider
        with tabs[2]:
            st.markdown("**Commandes POS — En attente de validation**")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            if df_cmd.empty or 'Statut' not in df_cmd.columns:
                st.info("Aucune commande en attente ou colonne 'Statut' manquante.")
            else:
                df_pending = df_cmd[df_cmd['Statut'].astype(str).str.strip() == 'En attente']
                if df_pending.empty:
                    st.info("Aucune commande en attente.")
                else:
                    st.dataframe(df_pending, use_container_width=True)
                    st.markdown("**Actions sur chaque ligne**")
                    for i, r in df_pending.iterrows():
                        cols_to_edit = ['Quantite']
                        for col in cols_to_edit:
                            new_val = st.number_input(f"{r['ID']} — Modifier {col}", value=int(r[col]), key=f"{r['ID']}_{col}")
                            r[col] = new_val
                        btn_accept = st.button(f"Valider la commande {r['ID']}", key=f"valider_{r['ID']}")
                        btn_cancel = st.button(f"Annuler la commande {r['ID']}", key=f"annuler_{r['ID']}")
                        if btn_accept:
                            try:
                                sh = client.open_by_key(SPREADSHEET_ID)
                                ws = sh.worksheet(SHEET_COMMANDES)
                                cell = ws.find(str(r['ID']))
                                row_no = cell.row
                                update_cell(SHEET_COMMANDES, row_no, 'Quantite', r['Quantite'])
                                update_cell(SHEET_COMMANDES, row_no, 'Statut', 'Validée')
                                update_cell(SHEET_COMMANDES, row_no, 'Date_validation', str(datetime.now()))
                                update_cell(SHEET_COMMANDES, row_no, 'Valide_par', st.session_state.user_email)
                                st.success(f"Commande {r['ID']} validée.")
                                st.experimental_rerun()
                            except:
                                st.error("Impossible de valider la commande.")
                        if btn_cancel:
                            try:
                                sh = client.open_by_key(SPREADSHEET_ID)
                                ws = sh.worksheet(SHEET_COMMANDES)
                                cell = ws.find(str(r['ID']))
                                row_no = cell.row
                                update_cell(SHEET_COMMANDES, row_no, 'Statut', 'Annulée')
                                st.success(f"Commande {r['ID']} annulée.")
                                st.experimental_rerun()
                            except:
                                st.error("Impossible d'annuler la commande.")

        # État des ventes
        with tabs[3]:
            st.markdown("**État des ventes (validées)**")
            if 'Statut' in df_cmd.columns:
                df_valid = df_cmd[df_cmd['Statut'].astype(str).str.strip() == 'Validée']
                if df_valid.empty:
                    st.info("Aucune vente validée.")
                else:
                    st.dataframe(df_valid, use_container_width=True)

    # -----------------------------
    # Espace Prévendeur
    # -----------------------------
    elif st.session_state.user_role == 'PreVendeur':
        st.subheader("Espace Prévendeur — Prise de commandes POS")
        tabs = st.tabs(["Plan de visite","Saisie commande","Historique commandes"])

        with tabs[0]:
            st.markdown("**Plan de visite du jour**")
            if df_list_pos.empty or 'Date_Visite' not in df_list_pos.columns:
                st.info("Aucun POS prévu ou colonne 'Date_Visite' manquante.")
            else:
                df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
                today = datetime.now().strftime('%Y-%m-%d')
                df_today = df_list_pos[df_list_pos['Date_Visite']==today]
                if df_today.empty:
                    st.info("Aucun POS à visiter aujourd'hui.")
                else:
                    st.dataframe(df_today[['Code_POS','Nom_POS','Adresse','Wilaya']], use_container_width=True)

        with tabs[1]:
            st.markdown("**Saisie d'une commande**")
            pos_options = df_today['Code_POS'].dropna().tolist() if not df_today.empty else []
            if pos_options:
                code_pos = st.selectbox("POS à commander", pos_options)
                produit_vente = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input("Produit *")
                quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1, value=1)
                if st.button("Ajouter commande"):
                    cmd_id = str(uuid.uuid4())
                    row = [cmd_id, str(datetime.now()), code_pos, str(produit_vente), int(quantite_vente),
                           st.session_state.user_code_vendeur, 'En attente', '', '']
                    append_row(SHEET_COMMANDES, row)
                    st.success(f"Commande ajoutée avec ID {cmd_id}")
                    st.session_state.commande_submitted = True

            if st.session_state.commande_submitted:
                df_cmd = load_sheet_df(SHEET_COMMANDES)
                st.markdown("**Dernières commandes**")
                st.dataframe(df_cmd.tail(10), use_container_width=True)
                st.session_state.commande_submitted = False

        with tabs[2]:
            st.markdown("**Historique commandes**")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            if df_cmd.empty or 'Code_Vendeur' not in df_cmd.columns:
                st.info("Aucune commande pour votre code vendeur.")
            else:
                df_user_cmd = df_cmd[df_cmd['Code_Vendeur'].astype(str).str.strip()==st.session_state.user_code_vendeur]
                st.dataframe(df_user_cmd, use_container_width=True)

    else:
        st.warning("Rôle non reconnu. Vérifie la feuille 'Utilisateurs'.")
