import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid

# -----------------------------
# Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="TSS - Distributeur", layout="wide")
st.title("📊 TSS - Distribution (Distributeur → POS → Client)")

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

# ID de ta feuille Google (remplace si besoin)
SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# utilitaires génériques pour Google Sheets
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
    """Retourne l'index (1-based, en tenant compte de l'en-tête) de la première ligne où column_name == value
    Si non trouvé retourne None"""
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
# Noms des feuilles (doivent exister exactement comme ci-dessous)
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_STOCK_POS = "Stock_POS"
SHEET_COMMANDES = "Commandes_POS"
SHEET_VENTES = "Ventes_ClientFinal"

# Chargements initiaux (pandas)
df_users = load_sheet_df(SHEET_USERS)
df_produits = load_sheet_df(SHEET_PRODUITS)
df_list_pos = load_sheet_df(SHEET_LIST_POS)
df_list_vendeur = load_sheet_df(SHEET_LIST_VENDEUR)

# produits dispo
produits_dispo = df_produits['Nom Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# Authentification simple (selectbox)
# -----------------------------
st.sidebar.header("Connexion")
if df_users.empty:
    st.sidebar.error("La feuille 'Utilisateurs' est vide ou introuvable. Merci de la configurer.")
    st.stop()

user_email = st.sidebar.selectbox("Sélectionnez votre email", df_users['Email'].tolist())
user_row = df_users[df_users['Email'] == user_email].iloc[0]
user_name = user_row.get('Nom', 'Utilisateur')
user_role = user_row.get('Role', 'POS')
user_code_pos = user_row.get('Code_POS', '')
user_code_vendeur = user_row.get('Code_Vendeur', '')

st.sidebar.markdown(f"**{user_name}** — {user_role}")

# -----------------------------
# Helper: calculer stock courant (distributeur ou POS)
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


@st.cache_data(ttl=10)
def compute_stock_pos(code_pos=None):
    df = load_sheet_df(SHEET_STOCK_POS)
    if df.empty:
        return pd.DataFrame(columns=['Code_POS','Produit','Stock'])
    df['Quantite_entree'] = pd.to_numeric(df['Quantite_entree'].fillna(0))
    df['Quantite_sortie'] = pd.to_numeric(df['Quantite_sortie'].fillna(0))
    grp = df.groupby(['Code_POS','Produit']).agg({'Quantite_entree':'sum','Quantite_sortie':'sum'}).reset_index()
    grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
    if code_pos:
        grp = grp[grp['Code_POS'] == code_pos]
    return grp[['Code_POS','Produit','Stock']]

# -----------------------------
# Interface selon rôle
# -----------------------------
if user_role == 'ADV':
    st.header("Espace ADV — Gestion stock & validation commandes")

    tabs = st.tabs(["📥 Ajouter stock distributeur","📋 Commandes en attente","📦 État stock distributeur"])

    # Onglet 1: Ajouter stock distributeur
    with tabs[0]:
        st.subheader("Ajouter entrée stock distributeur")
        col1,col2 = st.columns([2,1])
        with col1:
            produit = st.selectbox("Produit", produits_dispo)
            qty = st.number_input("Quantité entrée", min_value=1, step=1, value=1)
            motif = st.text_input("Motif (ex: Achat fournisseur)")
        with col2:
            if st.button("Ajouter au stock (Distributeur)"):
                today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ref = str(uuid.uuid4())
                append_row(SHEET_STOCK_DIST, [today, produit, qty, 0, motif, '', ref])
                st.success(f"+{qty} {produit} ajouté au stock distributeur.")
                compute_stock_distributeur.clear()

    # Onglet 2: Commandes en attente
    with tabs[1]:
        st.subheader("Commandes POS — En attente")
        df_cmd = load_sheet_df(SHEET_COMMANDES)
        if df_cmd.empty:
            st.info("Aucune commande enregistrée.")
        else:
            df_pending = df_cmd[df_cmd['Statut'] == 'En attente']
            if df_pending.empty:
                st.info("Aucune commande en attente.")
            else:
                st.dataframe(df_pending[['ID_Commande','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur']])
                sel = st.text_input("ID_Commande à valider (copier-coller)")
                if st.button("Valider la commande sélectionnée"):
                    if not sel:
                        st.error("Merci de renseigner l'ID de la commande à valider.")
                    else:
                        row_idx = find_row_index(SHEET_COMMANDES, 'ID_Commande', sel)
                        if not row_idx:
                            st.error("Commande non trouvée.")
                        else:
                            # lire la commande
                            df_all = load_sheet_df(SHEET_COMMANDES)
                            cmd = df_all[df_all['ID_Commande'] == sel].iloc[0]
                            produit = cmd['Produit']
                            quantite = int(cmd['Quantite'])
                            code_pos = cmd['Code_POS']
                            today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            ref = str(uuid.uuid4())
                            # 1) sortie stock distributeur
                            append_row(SHEET_STOCK_DIST, [today, produit, 0, quantite, 'Livraison POS', code_pos, ref])
                            # 2) entree stock POS
                            append_row(SHEET_STOCK_POS, [today, code_pos, produit, quantite, 0, 'Distributeur', ref])
                            # 3) mettre à jour la commande
                            update_cell(SHEET_COMMANDES, row_idx, 'Statut', 'Livré')
                            update_cell(SHEET_COMMANDES, row_idx, 'Date_validation', today)
                            update_cell(SHEET_COMMANDES, row_idx, 'Valide_par', user_email)
                            st.success(f"Commande {sel} validée et stock mis à jour.")
                            compute_stock_distributeur.clear()
                            compute_stock_pos.clear()

    # Onglet 3: Etat stock distributeur
    with tabs[2]:
        st.subheader("État du stock distributeur")
        st.dataframe(compute_stock_distributeur(), use_container_width=True)


elif user_role == 'PreVendeur' or user_role == 'PreVendeur'.lower():
    st.header("Espace Prévendeur — Prise de commandes POS")

    tabs = st.tabs(["📅 Plan de visite","📝 Saisir commande","📜 Historique commandes"])

    # Plan de visite
    with tabs[0]:
        st.subheader("Plan de visite du jour")
        df_pos = df_list_pos.copy()
        if df_pos.empty:
            st.info("La table ListofPOS est vide.")
        else:
            today_str = datetime.now().strftime('%Y-%m-%d')
            df_today = df_pos[df_pos['Date_Visite'] == today_str]
            # filtrer par vendeur
            if 'Code_Vendeur' in df_pos.columns and user_code_vendeur:
                df_today = df_today[df_today['Code_Vendeur'] == user_code_vendeur]
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
            append_row(SHEET_COMMANDES, [id_cmd, today, code_pos, produit, quantite, user_code_vendeur or user_email, 'En attente', '', ''])
            st.success(f"Commande {id_cmd} enregistrée (En attente).")

    # Historique commandes
    with tabs[2]:
        st.subheader("Historique des commandes saisies")
        df_cmd = load_sheet_df(SHEET_COMMANDES)
        if df_cmd.empty:
            st.info("Aucune commande enregistrée.")
        else:
            # filtrer par vendeur
            df_my = df_cmd[df_cmd['Code_Vendeur'] == (user_code_vendeur or user_email)]
            st.dataframe(df_my[['ID_Commande','Date_commande','Code_POS','Produit','Quantite','Statut']])


elif user_role == 'POS' or user_role == 'Pos' or user_role == 'pos':
    st.header("Espace POS — Ventes au client final & stock POS")

    tabs = st.tabs(["📦 Stock POS","💰 Enregistrer vente client","📄 Historique ventes"])

    # Stock POS
    with tabs[0]:
        st.subheader(f"Stock — {user_code_pos}")
        stock = compute_stock_pos(user_code_pos)
        if stock.empty:
            st.info("Aucun stock pour ce POS.")
        else:
            st.dataframe(stock, use_container_width=True)

    # Enregistrer vente client
    with tabs[1]:
        st.subheader("Enregistrer une vente au client final")
        produit = st.selectbox("Produit", sorted(stock['Produit'].unique().tolist()) if not stock.empty else produits_dispo)
        quantite = st.number_input("Quantité vendue", min_value=1, step=1, value=1)
        # prix: chercher dans produits
        prix_unitaire = 0
        if not df_produits.empty and produit in df_produits['Nom Produit'].values:
            prix_unitaire = float(df_produits[df_produits['Nom Produit'] == produit]['Prix POS'].values[0])
        total_ttc = int(round(prix_unitaire * quantite * 1.19,0)) if prix_unitaire else 0
        nom_client = st.text_input("Nom du client")
        tel_client = st.text_input("Téléphone client")
        montant_paye = st.number_input("Montant payé", min_value=0, max_value=total_ttc if total_ttc else 9999999, value=0, step=1)
        if st.button("Enregistrer la vente"):
            # vérifier stock disponible
            stock_df = compute_stock_pos(user_code_pos)
            available = 0
            if not stock_df.empty and produit in stock_df['Produit'].values:
                available = int(stock_df[stock_df['Produit']==produit]['Stock'].values[0])
            if available < quantite:
                st.error(f"Stock insuffisant pour {produit}. Disponible: {available}")
            else:
                today = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                ref = str(uuid.uuid4())
                # 1) enregistrer vente
                append_row(SHEET_VENTES, [today, user_code_pos, produit, quantite, prix_unitaire, total_ttc, montant_paye, total_ttc - montant_paye, nom_client, tel_client, '', ref])
                # 2) mettre une ligne de sortie dans Stock_POS
                append_row(SHEET_STOCK_POS, [today, user_code_pos, produit, 0, quantite, 'Vente client final', ref])
                st.success("Vente enregistrée et stock mis à jour.")
                compute_stock_pos.clear()

    # Historique ventes
    with tabs[2]:
        st.subheader("Historique des ventes du POS")
        df_ventes = load_sheet_df(SHEET_VENTES)
        if df_ventes.empty:
            st.info("Aucune vente enregistrée.")
        else:
            df_my = df_ventes[df_ventes['Code_POS'] == user_code_pos]
            st.dataframe(df_my[['Date','Produit','Quantite','Total_TTC','Montant_paye','Reste_a_payer','Nom_Client','Tel_Client']])

else:
    st.warning("Rôle non reconnu. Vérifie la feuille Utilisateurs.")

# -----------------------------
# NOTE: Améliorations futures
# - Ajouter vérification de permissions plus stricte
# - Générer PDF facture
# - Ajouter logs et tableaux de bord Power BI
# -----------------------------
