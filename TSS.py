import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from fpdf import FPDF
import io
from num2words import num2words

# -----------------------------
# ⚙️ Configuration Streamlit
# -----------------------------
st.set_page_config(page_title="Showroom Stock & Vente", layout="wide")
st.title("📊 Gestion Showroom")

# -----------------------------
# 🔹 Connexion Google Sheets
# -----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = st.secrets["google"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(creds)

# Nouvelle ID de Google Sheet
SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

try:
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    st.success("✅ Connexion Google Sheets réussie !")
except Exception as e:
    st.error(f"❌ Erreur de connexion Google Sheets : {e}")

# -----------------------------
# 🔹 Charger une feuille
# -----------------------------
@st.cache_data(ttl=10)
def load_sheet(sheet_name):
    try:
        sheet = spreadsheet.worksheet(sheet_name)
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erreur lors du chargement de la feuille '{sheet_name}': {e}")
        return pd.DataFrame()

# -----------------------------
# 🔹 Données initiales
# -----------------------------
df_produits = load_sheet("Produits")
produits_dispo = df_produits['Produit'].dropna().tolist() if not df_produits.empty else []

# -----------------------------
# 🔹 Gestion des onglets
# -----------------------------
tabs_labels = ["🛒 Ajouter Stock", "💰 Enregistrer Vente", "📦 État Stock", "📄 Historique Ventes", "💳 Paiements partiels"]
if "active_tab" not in st.session_state:
    st.session_state.active_tab = 0
if "panier" not in st.session_state:
    st.session_state.panier = []

tab_choice = st.radio("Choisir l'onglet", tabs_labels, index=st.session_state.active_tab)
st.session_state.active_tab = tabs_labels.index(tab_choice)

# -----------------------------
# Onglet 1 : Ajouter Stock
# -----------------------------
if tab_choice == "🛒 Ajouter Stock":
    st.header("Ajouter du stock")
    with st.form("form_stock"):
        produit_stock = st.selectbox("Produit *", produits_dispo)
        prix_achat = float(df_produits.loc[df_produits['Produit'] == produit_stock, 'Prix unitaire'].values[0]) if not df_produits.empty else 0.0
        quantite_stock = st.number_input("Quantité achetée", min_value=1, step=1)
        if st.form_submit_button("Ajouter au stock"):
            row = [str(datetime.now()), produit_stock, quantite_stock, prix_achat]
            spreadsheet.worksheet("Stock").append_row(row)
            st.success(f"{quantite_stock} {produit_stock} ajouté(s) au stock.")

# -----------------------------
# Onglet 2 : Enregistrer Vente
# -----------------------------
elif tab_choice == "💰 Enregistrer Vente":
    st.header("Enregistrer une vente multi-produits")

    produit_vente = st.selectbox("Produit vendu *", produits_dispo)
    if produit_vente:
        prix_unitaire = float(df_produits.loc[df_produits['Produit'] == produit_vente, 'Prix unitaire'].values[0])
    else:
        prix_unitaire = 0.0

    quantite_vente = st.number_input("Quantité vendue *", min_value=1, step=1)
    total_ht = prix_unitaire * quantite_vente
    total_ttc = int(round(total_ht * 1.19, 0))
    st.write(f"Prix unitaire : {prix_unitaire} DA | 💰 Total TTC : {total_ttc} DA")

    client_nom = st.text_input("Nom du client *")
    client_email = st.text_input("Email du client")
    client_tel = st.text_input("Téléphone du client *")
    client_rc = st.text_input("RC du client")
    client_nif = st.text_input("NIF du client")
    client_art = st.text_input("ART du client")
    client_adresse = st.text_input("Adresse du client")

    montant_paye = st.number_input("Montant payé par le client", min_value=0, max_value=total_ttc, value=0, step=1)
    reste_a_payer = total_ttc - montant_paye
    st.write(f"Reste à payer : {reste_a_payer} DA")

    generer_facture = st.checkbox("Générer une facture PDF")

    if st.button("Ajouter au panier"):
        if not produit_vente or quantite_vente <= 0 or not client_nom.strip() or not client_tel.strip():
            st.error("⚠️ Merci de remplir tous les champs obligatoires.")
        else:
            st.session_state.panier.append({
                "Produit": produit_vente,
                "Quantité": quantite_vente,
                "Prix unitaire": prix_unitaire,
                "Total HT": total_ht,
                "Total TTC": total_ttc,
                "Montant payé": montant_paye,
                "Reste à payer": reste_a_payer,
                "Client Nom": client_nom,
                "Client Email": client_email,
                "Client Tel": client_tel,
                "Client RC": client_rc,
                "Client NIF": client_nif,
                "Client ART": client_art,
                "Client Adresse": client_adresse
            })
            st.success(f"{quantite_vente} x {produit_vente} ajouté(s) au panier.")

    if st.session_state.panier:
        st.subheader("Panier actuel")
        df_panier = pd.DataFrame(st.session_state.panier)
        st.dataframe(df_panier[['Produit', 'Quantité', 'Prix unitaire', 'Total HT', 'Total TTC', 'Montant payé', 'Reste à payer']], use_container_width=True, hide_index=True)

# -----------------------------
# Onglet 3 : État Stock
# -----------------------------
elif tab_choice == "📦 État Stock":
    st.header("État du stock")
    df_stock = load_sheet("Stock")
    df_ventes = load_sheet("Ventes")
    if not df_stock.empty:
        stock_reel = df_stock.groupby("Produit")["Quantité"].sum().reset_index()
        if not df_ventes.empty:
            ventes_group = df_ventes.groupby("Produit")["Quantité"].sum().reset_index()
            stock_reel = stock_reel.merge(ventes_group, on="Produit", how="left", suffixes=('', '_vendu'))
            stock_reel['Quantité_vendu'] = stock_reel['Quantité_vendu'].fillna(0)
            stock_reel['Stock restant'] = stock_reel['Quantité'] - stock_reel['Quantité_vendu']
        else:
            stock_reel['Stock restant'] = stock_reel['Quantité']
        st.dataframe(stock_reel[['Produit', 'Stock restant']], use_container_width=True)
    else:
        st.write("Aucun stock enregistré.")

# -----------------------------
# Onglet 4 : Historique Ventes
# -----------------------------
elif tab_choice == "📄 Historique Ventes":
    st.header("Historique des ventes")
    df_ventes = load_sheet("Ventes")
    if not df_ventes.empty:
        st.dataframe(df_ventes, use_container_width=True)
    else:
        st.write("Aucune vente enregistrée.")

# -----------------------------
# Onglet 5 : Paiements partiels
# -----------------------------
elif tab_choice == "💳 Paiements partiels":
    st.header("État des paiements partiels")
    df_ventes = load_sheet("Ventes")
    if not df_ventes.empty:
        df_partiels = df_ventes[df_ventes["Reste à payer"] > 0]
        if not df_partiels.empty:
            st.dataframe(df_partiels[["Produit", "Nom", "Client Tel", "Total TTC", "Montant payé", "Reste à payer"]], use_container_width=True)
        else:
            st.write("Aucun paiement partiel en attente.")
    else:
        st.write("Aucune vente enregistrée.")
