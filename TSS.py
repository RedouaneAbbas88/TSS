import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import uuid
import time

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

# credentials via st.secrets["google"]
try:
    creds_dict = st.secrets.get("google")
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
except Exception as e:
    st.error("Erreur credentials Google Sheets. Vérifie st.secrets['google'].")
    st.stop()

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

# -----------------------------
# Feuilles (modifie si besoin)
# -----------------------------
SHEET_USERS = "Utilisateurs"
SHEET_PRODUITS = "Produits"
SHEET_LIST_POS = "ListofPOS"
SHEET_LIST_VENDEUR = "ListofVendeur"
SHEET_STOCK_DIST = "Stock_Distributeur"
SHEET_COMMANDES = "Commandes_POS"

# -----------------------------
# Utilitaires Google Sheets (cache optimisé)
# -----------------------------
@st.cache_data(ttl=90)
def load_sheet_cached(name: str):
    """Charge et nettoie une feuille; mise en cache pour réduire les appels."""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(name)
        records = ws.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return df
        df.columns = df.columns.str.strip()
        # strip all string cells
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except Exception as e:
        # Elevant message mais retourne df vide
        st.warning(f"Impossible de charger la feuille '{name}' : {e}")
        return pd.DataFrame()

def clear_sheets_cache():
    """Invalidate cache after writes so next read fetches fresh data."""
    try:
        st.cache_data.clear()
    except Exception:
        # Streamlit version safety
        pass

def append_row(sheet_name: str, row_values: list):
    """Ajoute une ligne puis invalide le cache."""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        ws.append_row(row_values)
        # petit délai pour laisser l'API appliquer l'écriture
        time.sleep(0.25)
        clear_sheets_cache()
        return True, None
    except Exception as e:
        return False, str(e)

def update_cell(sheet_name: str, row: int, col_name: str, new_value):
    """Met à jour une cellule (row is 1-indexed), invalide cache."""
    try:
        sh = client.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(sheet_name)
        headers = [h.strip() for h in ws.row_values(1)]
        try:
            col_idx = headers.index(col_name) + 1
        except ValueError:
            return False, f"Colonne '{col_name}' introuvable dans {sheet_name}"
        ws.update_cell(row, col_idx, new_value)
        time.sleep(0.25)
        clear_sheets_cache()
        return True, None
    except Exception as e:
        return False, str(e)

# -----------------------------
# Calcul stock (sans appeler trop souvent)
# -----------------------------
def compute_stock_from_df(df_stock: pd.DataFrame) -> pd.DataFrame:
    if df_stock.empty:
        return pd.DataFrame(columns=['Produit', 'Stock'])
    # normalisation colonnes
    df = df_stock.copy()
    df.columns = df.columns.str.strip()
    if 'Produit' not in df.columns:
        return pd.DataFrame(columns=['Produit', 'Stock'])
    # détecter colonnes quantité entrée/sortie
    col_in = None
    col_out = None
    for c in df.columns:
        key = c.lower().replace(" ", "").replace("_","")
        if key in ('quantiteentree','quantite_entree','entree','qtyin','qty_in','quantitein'):
            col_in = c
        if key in ('quantitesortie','quantite_sortie','sortie','qtyout','qty_out','quantiteout'):
            col_out = c
    if col_in is None:
        df['Quantite_entree'] = 0
    else:
        df['Quantite_entree'] = pd.to_numeric(df[col_in].fillna(0))
    if col_out is None:
        df['Quantite_sortie'] = 0
    else:
        df['Quantite_sortie'] = pd.to_numeric(df[col_out].fillna(0))
    grp = df.groupby('Produit', as_index=False).agg({'Quantite_entree':'sum','Quantite_sortie':'sum'})
    grp['Stock'] = grp['Quantite_entree'] - grp['Quantite_sortie']
    return grp[['Produit','Stock']]

# -----------------------------
# Chargement groupé (utilisé pour initialisation rapide)
# -----------------------------
def load_all():
    return {
        "users": load_sheet_cached(SHEET_USERS),
        "produits": load_sheet_cached(SHEET_PRODUITS),
        "list_pos": load_sheet_cached(SHEET_LIST_POS),
        "list_vendeur": load_sheet_cached(SHEET_LIST_VENDEUR),
        "stock_dist": load_sheet_cached(SHEET_STOCK_DIST),
        "commandes": load_sheet_cached(SHEET_COMMANDES)
    }

# -----------------------------
# Initialisation session_state
# -----------------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ''
    st.session_state.user_role = ''
    st.session_state.user_name = ''
    st.session_state.user_code_vendeur = ''
if 'just_added_stock' not in st.session_state:
    st.session_state.just_added_stock = False
if 'just_added_commande' not in st.session_state:
    st.session_state.just_added_commande = False
if 'just_validated' not in st.session_state:
    st.session_state.just_validated = False

# -----------------------------
# LOAD initial (cache-backed)
# -----------------------------
data = load_all()
df_users = data["users"]
df_produits = data["produits"]
df_list_pos = data["list_pos"]
df_list_vendeur = data["list_vendeur"]
df_stock_dist = data["stock_dist"]
df_commandes = data["commandes"]

# produits dispo tolerant
produits_dispo = []
if not df_produits.empty:
    for col in ('Nom Produit','NomProduit','Produit','Name'):
        if col in df_produits.columns:
            produits_dispo = df_produits[col].dropna().tolist()
            break

# -----------------------------
# Interface connexion (mot de passe en clair pour dev/test)
# -----------------------------
st.sidebar.header("Connexion")
if not st.session_state.logged_in:
    email_input = st.sidebar.text_input("Email")
    password_input = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        if df_users.empty:
            st.sidebar.error("Feuille 'Utilisateurs' vide ou introuvable.")
        else:
            if 'Email' not in df_users.columns or 'Password' not in df_users.columns:
                st.sidebar.error("Feuille 'Utilisateurs' doit contenir les colonnes 'Email' et 'Password'.")
            else:
                mask = df_users['Email'].astype(str).str.strip() == email_input.strip()
                if mask.sum() == 0:
                    st.sidebar.error("Email non reconnu.")
                else:
                    user = df_users[mask].iloc[0]
                    pw_sheet = str(user.get('Password','')).strip()
                    if pw_sheet != password_input.strip():
                        st.sidebar.error("Mot de passe incorrect.")
                    else:
                        # Login OK
                        st.session_state.logged_in = True
                        st.session_state.user_email = user.get('Email','').strip()
                        st.session_state.user_role = user.get('Role','PreVendeur')
                        st.session_state.user_name = user.get('Nom', user.get('Name','Utilisateur'))
                        st.session_state.user_code_vendeur = user.get('Code_Vendeur','')
                        st.sidebar.success(f"Connecté : {st.session_state.user_name} — {st.session_state.user_role}")
                        # Recharger les données en mémoire (cache invalidé si nécessaire)
                        data = load_all()
                        df_produits = data["produits"]
                        df_list_pos = data["list_pos"]
                        df_stock_dist = data["stock_dist"]
                        df_commandes = data["commandes"]

# -----------------------------
# Interface principale
# -----------------------------
if st.session_state.logged_in:
    st.header(f"📊 TSS - Distribution — {st.session_state.user_name} ({st.session_state.user_role})")
    st.write("")  # espace

    # refresh local variables from cache (cheap)
    data = load_all()
    df_produits = data["produits"]
    df_list_pos = data["list_pos"]
    df_stock_dist = data["stock_dist"]
    df_commandes = data["commandes"]

    # recalc produits dispo
    produits_dispo = []
    if not df_produits.empty:
        for col in ('Nom Produit','NomProduit','Produit','Name'):
            if col in df_produits.columns:
                produits_dispo = df_produits[col].dropna().tolist()
                break

    # ADV
    if st.session_state.user_role == 'ADV':
        st.subheader("Espace ADV — Gestion stock & validation commandes")
        adv_tabs = st.tabs(["Ajouter Stock","État Stock","Commandes à valider","État des ventes"])

        # --- Ajouter Stock ---
        with adv_tabs[0]:
            st.markdown("**Ajouter du stock au distributeur**")
            with st.form("form_add_stock"):
                produit_stock = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input("Produit *")
                quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1, value=1)
                prix_achat = st.text_input("Prix unitaire (optionnel)", value="")
                submitted = st.form_submit_button("Ajouter au stock")
                if submitted:
                    prix_val = float(prix_achat) if str(prix_achat).strip() != "" else 0.0
                    row = [str(datetime.now()), str(produit_stock), int(quantite_stock), prix_val]
                    ok, err = append_row(SHEET_STOCK_DIST, row)
                    if not ok:
                        st.error(f"Erreur ajout stock : {err}")
                    else:
                        st.success(f"{quantite_stock} x {produit_stock} ajouté(s) au stock distributeur.")
                        st.session_state.just_added_stock = True

            # affichage immédiat si ajouté
            if st.session_state.just_added_stock:
                df_stock_dist = load_sheet_cached(SHEET_STOCK_DIST)  # fresh because cache cleared by append_row
                df_stock_view = compute_stock_from_df(df_stock_dist)
                st.markdown("**Stock actuel (mis à jour)**")
                st.dataframe(df_stock_view, use_container_width=True)
                st.session_state.just_added_stock = False

        # --- État Stock ---
        with adv_tabs[1]:
            st.markdown("**État du stock**")
            df_stock_view = compute_stock_from_df(df_stock_dist)
            if df_stock_view.empty:
                st.info("Aucun stock enregistré.")
            else:
                st.dataframe(df_stock_view, use_container_width=True)

        # --- Commandes à valider ---
        with adv_tabs[2]:
            st.markdown("**Commandes POS — En attente de validation**")
            if df_commandes.empty:
                st.info("Aucune commande enregistrée.")
            else:
                if 'Statut' not in df_commandes.columns:
                    st.warning("La feuille Commandes_POS n'a pas la colonne 'Statut'.")
                else:
                    df_pending = df_commandes[df_commandes['Statut'].astype(str).str.strip() == 'En attente']
                    if df_pending.empty:
                        st.info("Aucune commande en attente.")
                    else:
                        # afficher tableau récap en premier pour visibilité
                        cols_show = [c for c in ['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur'] if c in df_commandes.columns]
                        st.dataframe(df_pending[cols_show], use_container_width=True)
                        # puis boutons individuels
                        for i, r in df_pending.iterrows():
                            st.markdown(f"**Commande ID : {r.get('ID')} — POS : {r.get('Code_POS','---')}**")
                            details = {k: r[k] for k in ['Produit','Quantite','Code_Vendeur'] if k in df_commandes.columns}
                            st.json(details)
                            key_btn = f"valider_{r.get('ID')}"
                            if st.button("Valider la commande", key=key_btn):
                                # essai trouver la ligne exacte via find (plus fiable) sinon fallback
                                row_no = None
                                try:
                                    sh = client.open_by_key(SPREADSHEET_ID)
                                    ws = sh.worksheet(SHEET_COMMANDES)
                                    cell = ws.find(str(r.get('ID')))
                                    row_no = cell.row
                                except Exception:
                                    row_no = i + 2  # fallback
                                ok, err = update_cell(SHEET_COMMANDES, row_no, 'Statut', 'Validée')
                                if not ok:
                                    st.error(f"Erreur mise à jour statut : {err}")
                                else:
                                    _, err2 = update_cell(SHEET_COMMANDES, row_no, 'Date_validation', str(datetime.now()))
                                    _, err3 = update_cell(SHEET_COMMANDES, row_no, 'Valide_par', st.session_state.user_email)
                                    st.success(f"Commande {r.get('ID')} validée.")
                                    st.session_state.just_validated = True

            # si on a validé => montrer récap validées
            if st.session_state.just_validated:
                df_commandes = load_sheet_cached(SHEET_COMMANDES)
                if 'Statut' in df_commandes.columns:
                    df_valid = df_commandes[df_commandes['Statut'].astype(str).str.strip() == 'Validée']
                    if not df_valid.empty:
                        cols = [c for c in ['ID','Date_commande','Code_POS','Produit','Quantite','Valide_par'] if c in df_valid.columns]
                        st.markdown("**Ventes validées (récap)**")
                        st.dataframe(df_valid[cols].tail(20), use_container_width=True)
                st.session_state.just_validated = False

        # --- État des ventes ---
        with adv_tabs[3]:
            st.markdown("**État des ventes (validées)**")
            df_commandes = load_sheet_cached(SHEET_COMMANDES)
            if 'Statut' in df_commandes.columns:
                df_valid = df_commandes[df_commandes['Statut'].astype(str).str.strip() == 'Validée']
                if df_valid.empty:
                    st.info("Aucune vente validée.")
                else:
                    cols = [c for c in ['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Date_validation','Valide_par'] if c in df_valid.columns]
                    st.dataframe(df_valid[cols], use_container_width=True)
            else:
                st.warning("La feuille Commandes_POS n'a pas la colonne 'Statut'.")

    # -----------------------------
    # Prévendeur
    # -----------------------------
    elif st.session_state.user_role == 'PreVendeur':
        st.subheader("Espace Prévendeur — Prise de commandes POS")
        pre_tabs = st.tabs(["Plan de visite","Saisie commande","Historique commandes"])

        # Plan de visite
        with pre_tabs[0]:
            st.markdown("**Plan de visite du jour**")
            if df_list_pos.empty:
                st.info("La table ListofPOS est vide ou introuvable.")
            else:
                if 'Date_Visite' in df_list_pos.columns:
                    df_list_pos_local = df_list_pos.copy()
                    df_list_pos_local['Date_Visite'] = pd.to_datetime(df_list_pos_local['Date_Visite'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
                    today = datetime.now().strftime('%Y-%m-%d')
                    df_today = df_list_pos_local[df_list_pos_local['Date_Visite'] == today]
                    if df_today.empty:
                        st.info("Aucun POS à visiter aujourd'hui.")
                    else:
                        cols = [c for c in ['Code_POS','Nom_POS','Adresse','Wilaya','Date_Visite'] if c in df_today.columns]
                        st.dataframe(df_today[cols], use_container_width=True)
                else:
                    st.warning("La table ListofPOS n'a pas la colonne 'Date_Visite'.")

        # Saisie commande
        with pre_tabs[1]:
            st.markdown("**Saisie d'une commande**")
            pos_options = []
            if not df_list_pos.empty and 'Date_Visite' in df_list_pos.columns:
                df_list_pos_local = df_list_pos.copy()
                df_list_pos_local['Date_Visite'] = pd.to_datetime(df_list_pos_local['Date_Visite'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
                today = datetime.now().strftime('%Y-%m-%d')
                df_today = df_list_pos_local[df_list_pos_local['Date_Visite'] == today]
                if not df_today.empty and 'Code_POS' in df_today.columns:
                    pos_options = df_today['Code_POS'].dropna().tolist()
            if not pos_options:
                st.info("Aucun POS prévu aujourd'hui (ou colonne Code_POS manquante).")
            else:
                code_pos = st.selectbox("POS à commander", pos_options)
                produit_vente = st.selectbox("Produit *", produits_dispo) if produits_dispo else st.text_input("Produit *")
                quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1, value=1)
                if st.button("Ajouter commande"):
                    cmd_id = str(uuid.uuid4())
                    row = [cmd_id, str(datetime.now()), code_pos, str(produit_vente), int(quantite_vente), st.session_state.user_code_vendeur, 'En attente', '', '']
                    ok, err = append_row(SHEET_COMMANDES, row)
                    if not ok:
                        st.error(f"Erreur ajout commande : {err}")
                    else:
                        st.success(f"Commande ajoutée avec ID {cmd_id}")
                        st.session_state.just_added_commande = True

            # affichage immédiat des dernières commandes
            if st.session_state.just_added_commande:
                df_cmd = load_sheet_cached(SHEET_COMMANDES)
                cols = [c for c in ['ID','Date_commande','Code_POS','Produit','Quantite','Code_Vendeur','Statut'] if c in df_cmd.columns]
                st.markdown("**Dernières commandes (après ajout)**")
                st.dataframe(df_cmd[cols].tail(10), use_container_width=True)
                st.session_state.just_added_commande = False

        # Historique commandes
        with pre_tabs[2]:
            st.markdown("**Historique des commandes (votre code vendeur)**")
            df_cmd = load_sheet_cached(SHEET_COMMANDES)
            if df_cmd.empty:
                st.info("Aucune commande enregistrée.")
            else:
                if 'Code_Vendeur' in df_cmd.columns:
                    df_user_cmd = df_cmd[df_cmd['Code_Vendeur'].astype(str).str.strip() == str(st.session_state.user_code_vendeur).strip()]
                    if df_user_cmd.empty:
                        st.info("Aucune commande pour votre code vendeur.")
                    else:
                        cols = [c for c in ['ID','Date_commande','Code_POS','Produit','Quantite','Statut','Date_validation','Valide_par'] if c in df_user_cmd.columns]
                        st.dataframe(df_user_cmd[cols], use_container_width=True)
                else:
                    st.warning("La feuille Commandes_POS n'a pas la colonne 'Code_Vendeur'.")

    else:
        st.warning("Rôle non reconnu. Vérifie la feuille 'Utilisateurs'.")

# -----------------------------
# Fin
# -----------------------------
