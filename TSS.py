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

creds_dict = st.secrets.get("google")
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# Feuilles
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"


# -----------------------------
# Fonctions utilitaires
# -----------------------------
@st.cache_data(ttl=60)
def load_sheet_df_cached(sheet_name):
    return load_sheet_df(sheet_name)


def load_sheet_df(sheet_name):
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
    df = load_sheet_df_cached(SHEET_STOCK_DIST)
    if df.empty:
        return pd.DataFrame(columns=['Produit', 'Stock'])
    # Colonnes entrée/sortie
    col_in = [c for c in df.columns if 'entree' in c.lower().replace(" ", "")]
    col_out = [c for c in df.columns if 'sortie' in c.lower().replace(" ", "")]
    df['Quantite_entree'] = pd.to_numeric(df[col_in[0]].fillna(0)) if col_in else 0
    df['Quantite_sortie'] = pd.to_numeric(df[col_out[0]].fillna(0)) if col_out else 0
    grp = df.groupby('Produit', as_index=False).agg({'Quantite_entree': 'sum', 'Quantite_sortie': 'sum'})
    grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
    return grp[['Produit', 'Stock']]


# -----------------------------
# Session state
# -----------------------------
for key in ['logged_in', 'user_email', 'user_role', 'user_name', 'user_code_vendeur',
            'stock_submitted', 'commande_submitted', 'command_validated']:
    if key not in st.session_state:
        st.session_state[key] = False if 'submitted' in key or 'logged_in' in key or 'command_validated' in key else ''

# -----------------------------
# Login
# -----------------------------
st.sidebar.header("Connexion")
if not st.session_state.logged_in:
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        df_users = load_sheet_df_cached(SHEET_USERS)
        if df_users.empty:
            st.sidebar.error("Feuille 'Utilisateurs' vide ou introuvable.")
        else:
            if 'Email' not in df_users.columns or 'Password' not in df_users.columns:
                st.sidebar.error("La feuille 'Utilisateurs' doit contenir 'Email' et 'Password'.")
            else:
                mask = df_users['Email'].astype(str).str.strip() == email_input.strip()
                user_rows = df_users[mask]
                if user_rows.empty:
                    st.sidebar.error("Email non reconnu.")
                else:
                    user = user_rows.iloc[0]
                    if str(user['Password']).strip() != password_input.strip():
                        st.sidebar.error("Mot de passe incorrect.")
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_email = user.get('Email', '').strip()
                        st.session_state.user_role = user.get('Role', 'PreVendeur')
                        st.session_state.user_name = user.get('Nom', user.get('Name', 'Utilisateur'))
                        st.session_state.user_code_vendeur = user.get('Code_Vendeur', '')
                        st.sidebar.success(f"Connecté : {st.session_state.user_name} ({st.session_state.user_role})")

# -----------------------------
# Interface principale
# -----------------------------
if st.session_state.logged_in:
    st.header(f"📊 TSS - Distribution — {st.session_state.user_name} ({st.session_state.user_role})")

    df_produits = load_sheet_df_cached(SHEET_PRODUITS)
    df_list_pos = load_sheet_df_cached(SHEET_LIST_POS)
    produits_dispo = []
    if not df_produits.empty:
        for col_name in ('Nom Produit', 'NomProduit', 'Produit', 'Name'):
            if col_name in df_produits.columns:
                produits_dispo = df_produits[col_name].dropna().tolist()
                break

    # -----------------------------
    # ADV
    # -----------------------------
    if st.session_state.user_role == 'ADV':
        st.subheader("Espace ADV — Gestion stock & validation commandes")
        tabs = st.tabs(["Ajouter Stock", "État Stock", "Commandes à valider", "État des ventes"])

        # ---------- Ajouter Stock ----------
        with tabs[0]:
            st.markdown("**Ajouter du stock au distributeur**")
            with st.form("form_add_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input(
                    "Produit *")
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1, value=1)
                prix_achat = st.text_input("Prix unitaire (optionnel)", value="")
                submitted = st.form_submit_button("Ajouter au stock")
                if submitted:
                    row = [str(datetime.now()), str(produit_stock), int(quantite_stock),
                           float(prix_achat) if prix_achat.strip() else 0.0]
                    append_row(SHEET_STOCK_DIST, row)
                    st.success(f"{quantite_stock} x {produit_stock} ajouté(s) au stock distributeur.")
                    st.session_state.stock_submitted = True
            if st.session_state.stock_submitted:
                df_stock = compute_stock_distributeur()
                st.dataframe(df_stock, use_container_width=True)
                st.session_state.stock_submitted = False

        # ---------- État Stock ----------
        with tabs[1]:
            st.markdown("**État du stock**")
            df_stock = compute_stock_distributeur()
            if df_stock.empty:
                st.info("Aucun stock enregistré.")
            else:
                st.dataframe(df_stock, use_container_width=True)

        # ---------- Commandes à valider ----------
        with tabs[2]:
            st.markdown("**Commandes POS — En attente de validation**")
            df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
            if df_cmd.empty:
                st.info("Aucune commande enregistrée.")
            elif 'Statut' not in df_cmd.columns:
                st.warning("La feuille Commandes_POS n'a pas la colonne 'Statut'.")
            else:
                df_pending = df_cmd[df_cmd['Statut'].astype(str).str.strip() == 'En attente'].copy()
                if df_pending.empty:
                    st.info("Aucune commande en attente.")
                else:
                    cols_display = ['ID', 'Code_POS', 'Produit', 'Quantite', 'Code_Vendeur']
                    cols_display = [c for c in cols_display if c in df_pending.columns]
                    st.markdown("**Modifier la quantité si nécessaire puis cliquer sur Valider ou Annuler**")

                    edited_df = st.data_editor(
                        df_pending[cols_display],
                        num_rows="dynamic",
                        key="edit_pending_cmd",
                        use_container_width=True
                    )

                    # Boutons par ligne
                    for idx, row in edited_df.iterrows():
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if st.button("Valider", key=f"valider_{row['ID']}"):
                                try:
                                    ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_COMMANDES)
                                    cell = ws.find(str(row['ID']))
                                    row_no = cell.row
                                except:
                                    row_no = idx + 2
                                update_cell(SHEET_COMMANDES, row_no, 'Quantite', row['Quantite'])
                                update_cell(SHEET_COMMANDES, row_no, 'Statut', 'Validée')
                                update_cell(SHEET_COMMANDES, row_no, 'Date_validation', str(datetime.now()))
                                update_cell(SHEET_COMMANDES, row_no, 'Valide_par', st.session_state.user_email)
                                st.success(f"Commande {row['ID']} validée !")
                        with col2:
                            if st.button("Annuler", key=f"annuler_{row['ID']}"):
                                try:
                                    ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_COMMANDES)
                                    cell = ws.find(str(row['ID']))
                                    row_no = cell.row
                                except:
                                    row_no = idx + 2
                                update_cell(SHEET_COMMANDES, row_no, 'Statut', 'Annulée')
                                st.warning(f"Commande {row['ID']} annulée !")

        # ---------- État des ventes ----------
        with tabs[3]:
            st.markdown("**État des ventes (validées)**")
            df_cmd_valid = df_cmd[
                df_cmd['Statut'].astype(str).str.strip() == 'Validée'] if 'Statut' in df_cmd.columns else pd.DataFrame()
            if df_cmd_valid.empty:
                st.info("Aucune vente validée.")
            else:
                cols = [c for c in ['ID', 'Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Code_Vendeur', 'Statut',
                                    'Date_validation', 'Valide_par'] if c in df_cmd_valid.columns]
                st.dataframe(df_cmd_valid[cols], use_container_width=True)

    # -----------------------------
    # PreVendeur
    # -----------------------------
    elif st.session_state.user_role == 'PreVendeur':
        st.subheader("Espace Prévendeur — Prise de commandes POS")
        tabs = st.tabs(["Plan de visite", "Saisie commande", "Historique commandes"])

        # Plan de visite
        with tabs[0]:
            st.markdown("**Plan de visite du jour**")
            if df_list_pos.empty:
                st.info("Table ListofPOS vide ou introuvable.")
            elif 'Date_Visite' in df_list_pos.columns:
                df_list_pos['Date_Visite'] = pd.to_datetime(df_list_pos['Date_Visite'], dayfirst=True,
                                                            errors='coerce').dt.strftime('%Y-%m-%d')
                today = datetime.now().strftime('%Y-%m-%d')
                df_today = df_list_pos[df_list_pos['Date_Visite'] == today]
                if df_today.empty:
                    st.info("Aucun POS à visiter aujourd'hui.")
                else:
                    st.dataframe(df_today[['Code_POS', 'Nom_POS', 'Adresse', 'Wilaya']], use_container_width=True)

        # Saisie commande
        with tabs[1]:
            st.markdown("**Saisie d'une commande**")
            pos_options = df_list_pos[df_list_pos['Date_Visite'] == today][
                'Code_POS'].dropna().tolist() if not df_list_pos.empty and 'Date_Visite' in df_list_pos.columns else []
            if not pos_options:
                st.info("Aucun POS prévu aujourd'hui.")
            else:
                code_pos = st.selectbox("POS à commander", pos_options)
                produit_vente = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input(
                    "Produit *")
                quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1, value=1)
                if st.button("Ajouter commande"):
                    cmd_id = str(uuid.uuid4())
                    row = [cmd_id, str(datetime.now()), code_pos, str(produit_vente), int(quantite_vente),
                           st.session_state.user_code_vendeur, 'En attente', '', '']
                    append_row(SHEET_COMMANDES, row)
                    st.success(f"Commande ajoutée avec ID {cmd_id}")
                    st.session_state.commande_submitted = True
            if st.session_state.commande_submitted:
                df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
                cols = [c for c in ['ID', 'Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Code_Vendeur', 'Statut']
                        if c in df_cmd.columns]
                st.dataframe(df_cmd[cols].tail(10), use_container_width=True)
                st.session_state.commande_submitted = False

        # Historique commandes
        with tabs[2]:
            st.markdown("**Historique des commandes (votre code vendeur)**")
            df_cmd = load_sheet_df_cached(SHEET_COMMANDES)
            if df_cmd.empty:
                st.info("Aucune commande enregistrée.")
            elif 'Code_Vendeur' in df_cmd.columns:
                df_user_cmd = df_cmd[
                    df_cmd['Code_Vendeur'].astype(str).str.strip() == str(st.session_state.user_code_vendeur).strip()]
                if df_user_cmd.empty:
                    st.info("Aucune commande pour votre code vendeur.")
                else:
                    cols = [c for c in
                            ['ID', 'Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Statut', 'Date_validation',
                             'Valide_par'] if c in df_user_cmd.columns]
                    st.dataframe(df_user_cmd[cols], use_container_width=True)

