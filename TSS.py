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


# -----------------------------
# Noms des tables Google Sheet
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Chargement initial des données
# -----------------------------
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
        grp = df.groupby('Produit').agg({'Quantite_entree': 'sum', 'Quantite_sortie': 'sum'}).reset_index()
        grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
        return grp[['Produit', 'Stock']]


    stock_distributeur = compute_stock_distributeur()

    # -----------------------------
    # Interface ADV
    # -----------------------------
    if user_role == 'ADV':
        st.header("Espace ADV — Gestion stock & validation commandes")

        menu = st.tabs(["📦 Stock", "📝 Commandes", "📊 État des ventes", "📄 Historique commandes"])

        # ---------------- Stock
        with menu[0]:
            st.subheader("Stock Distributeur")
            st.dataframe(stock_distributeur, use_container_width=True)
            st.markdown("---")
            st.subheader("Ajouter du stock")
            produit_stock = st.selectbox("Produit", produits_dispo)
            quantite_stock = st.number_input("Quantité", min_value=1, step=1)
            if st.button("Ajouter au stock"):
                row = [str(datetime.now()), produit_stock, quantite_stock, 0]  # Prix optionnel
                append_row(SHEET_STOCK_DIST, row)
                st.success(f"{quantite_stock} x {produit_stock} ajouté au stock.")
                st.experimental_rerun()

        # ---------------- Commandes à valider
        with menu[1]:
            st.subheader("Commandes à valider")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_en_attente = df_cmd[df_cmd['Statut'] == "En attente"]

            if df_en_attente.empty:
                st.info("Aucune commande en attente.")
            else:
                # Afficher toutes les commandes en attente
                st.dataframe(
                    df_en_attente[['ID', 'Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Code_Vendeur', 'Statut']],
                    use_container_width=True)

                # Sélectionner la commande à valider
                cmd_id = st.selectbox("Sélectionner commande à valider", df_en_attente['ID'])
                cmd_row_index = find_row_index(SHEET_COMMANDES, 'ID', cmd_id)

                if st.button("Valider la commande"):
                    if cmd_row_index:
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Statut', 'Validée')
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Date_validation', str(datetime.now()))
                        update_cell(SHEET_COMMANDES, cmd_row_index, 'Valide_par', email_input)
                        st.success("Commande validée !")
                        st.experimental_rerun()
                    else:
                        st.error("Impossible de trouver la commande.")

        # ---------------- État des ventes
        with menu[2]:
            st.subheader("État des ventes validées")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            df_ventes = df_cmd[df_cmd['Statut'] == "Validée"] if not df_cmd.empty else pd.DataFrame()
            if df_ventes.empty:
                st.info("Aucune vente validée.")
            else:
                st.dataframe(df_ventes[['Date_commande', 'Code_POS', 'Produit', 'Quantite', 'Code_Vendeur', 'Statut',
                                        'Date_validation', 'Valide_par']], use_container_width=True)

        # ---------------- Historique commandes
        with menu[3]:
            st.subheader("Historique complet des commandes")
            df_cmd = load_sheet_df(SHEET_COMMANDES)
            st.dataframe(df_cmd, use_container_width=True)

    # -----------------------------
    # Interface Prévendeur
    # -----------------------------
    elif user_role == 'PreVendeur':
        st.header("Espace Prévendeur — Prise de commandes POS")

        st.subheader("Plan de visite du jour")
        df_pos_today = df_list_pos[df_list_pos['Date_Visite'] == datetime.now().strftime('%d/%m/%y')]
        if df_pos_today.empty:
            st.info("Aucun POS à visiter aujourd'hui.")
        else:
            st.dataframe(df_pos_today[['Code_POS', 'Nom_POS', 'Adresse', 'Wilaya']], use_container_width=True)

        st.markdown("---")
        st.subheader("Passer une commande")
        produit_vente = st.selectbox("Produit", produits_dispo)
        quantite_vente = st.number_input("Quantité", min_value=1, step=1)
        code_pos = st.selectbox("Sélectionner le POS", df_pos_today['Code_POS']) if not df_pos_today.empty else ""

        if st.button("Enregistrer la commande"):
            cmd_id = str(uuid.uuid4())
            row = [cmd_id, str(datetime.now()), code_pos, produit_vente, quantite_vente, user_code_vendeur,
                   'En attente', '', '']
            append_row(SHEET_COMMANDES, row)
            st.success("Commande enregistrée !")
            st.experimental_rerun()

        st.markdown("---")
        st.subheader("Historique de vos commandes")
        df_cmd = load_sheet_df(SHEET_COMMANDES)
        df_cmd_user = df_cmd[df_cmd['Code_Vendeur'] == user_code_vendeur] if not df_cmd.empty else pd.DataFrame()
        st.dataframe(df_cmd_user, use_container_width=True)

    else:
        st.warning("Rôle non reconnu. Vérifie la feuille Utilisateurs.")
