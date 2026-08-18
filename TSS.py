import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime

# =========================================================
# CONFIGURATION
# =========================================================
st.set_page_config(
    page_title="Data_Info",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.main-title {
    font-size: 30px;
    font-weight: 700;
    margin-bottom: 5px;
}
.small-title {
    color: #666;
    margin-bottom: 20px;
}
div[data-testid="stMetric"] {
    border: 1px solid #e5e7eb;
    padding: 12px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# GOOGLE SHEETS
# =========================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = "1SN02jxpV2oyc3tWItY9c2Kc_UEXfqTdtQSL9WgGAi3w"

SHEET_USERS = "Utilisateurs"
SHEET_POS = "POS"
SHEET_PRODUCTS = "Produits"
SHEET_PROFILE = "Profil_Client"
SHEET_DISTRIBUTION = "Distribution_Numerique"
SHEET_PRICES = "Releve_Prix"
SHEET_SURVEYS = "Enquetes"
SHEET_SURVEY_SUBJECTS = "Enquetes_Sujets"
SHEET_VISITS = "Visites_POS"
SHEET_OBJECTIVES = "Objectifs_POS"


@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["google"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)


client = get_client()


def get_ws(sheet_name):
    return client.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)


@st.cache_data(ttl=30)
def load_sheet(sheet_name):
    try:
        ws = get_ws(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if not df.empty:
            df.columns = df.columns.astype(str).str.strip()
        return df
    except Exception as e:
        return pd.DataFrame()


def append_row(sheet_name, row):
    ws = get_ws(sheet_name)
    ws.append_row(row, value_input_option="USER_ENTERED")
    load_sheet.clear()


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def unique_sorted(df, column):
    if df.empty or column not in df.columns:
        return []
    values = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
    )
    values = [v for v in values.unique().tolist() if v]
    return sorted(values)


def filter_products(products, marque="", categorie="", famille="", produit=""):
    if products.empty:
        return products

    result = products.copy()

    if marque and "Marque" in result.columns:
        result = result[result["Marque"].astype(str).str.strip() == marque]

    if categorie and "Catégorie" in result.columns:
        result = result[result["Catégorie"].astype(str).str.strip() == categorie]

    if famille and "Famille" in result.columns:
        result = result[result["Famille"].astype(str).str.strip() == famille]

    if produit and "Produit" in result.columns:
        result = result[result["Produit"].astype(str).str.strip() == produit]

    return result


# =========================================================
# SESSION / LOGIN
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "role" not in st.session_state:
    st.session_state.role = ""

if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if "user_id" not in st.session_state:
    st.session_state.user_id = ""


def logout():
    st.session_state.logged_in = False
    st.session_state.role = ""
    st.session_state.user_name = ""
    st.session_state.user_id = ""
    st.rerun()


# =========================================================
# LOGIN PAGE
# =========================================================
if not st.session_state.logged_in:

    st.markdown(
        "<div class='main-title'>📊 Data_Info</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<div class='small-title'>Market Data Collection & Analysis</div>",
        unsafe_allow_html=True
    )

    users = load_sheet(SHEET_USERS)

    if users.empty:
        st.error(
            "Impossible de charger la table Utilisateurs. "
            "Vérifiez le nom de la feuille et la connexion Google Sheets."
        )
        st.stop()

    if "Nom" not in users.columns or "Password" not in users.columns:
        st.error(
            "La table Utilisateurs doit contenir au minimum : "
            "ID_User, Nom, Email, Password, Role, Statut."
        )
        st.stop()

    users["Nom"] = users["Nom"].astype(str).str.strip()

    active_users = users.copy()

    if "Statut" in active_users.columns:
        active_users = active_users[
            active_users["Statut"].astype(str).str.lower().str.strip() != "inactif"
        ]

    names = sorted(active_users["Nom"].dropna().unique().tolist())

    with st.form("login_form"):
        st.subheader("🔐 Connexion")

        selected_name = st.selectbox(
            "Utilisateur",
            names if names else ["Aucun utilisateur"]
        )

        password = st.text_input(
            "Mot de passe",
            type="password"
        )

        login_button = st.form_submit_button(
            "Se connecter",
            use_container_width=True
        )

        if login_button:
            user = active_users[
                active_users["Nom"] == selected_name
            ]

            if user.empty:
                st.error("Utilisateur introuvable.")
            else:
                user = user.iloc[0]

                if clean_text(user["Password"]) != password.strip():
                    st.error("Mot de passe incorrect.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.user_name = clean_text(user["Nom"])
                    st.session_state.role = clean_text(
                        user.get("Role", "enqueteur")
                    ).lower()

                    st.session_state.user_id = clean_text(
                        user.get("ID_User", "")
                    )

                    st.rerun()

    st.stop()


# =========================================================
# LOAD MAIN DATA
# =========================================================
df_users = load_sheet(SHEET_USERS)
df_pos = load_sheet(SHEET_POS)
df_products = load_sheet(SHEET_PRODUCTS)
df_profile = load_sheet(SHEET_PROFILE)
df_distribution = load_sheet(SHEET_DISTRIBUTION)
df_prices = load_sheet(SHEET_PRICES)
df_surveys = load_sheet(SHEET_SURVEYS)
df_subjects = load_sheet(SHEET_SURVEY_SUBJECTS)
df_visits = load_sheet(SHEET_VISITS)
df_objectives = load_sheet(SHEET_OBJECTIVES)


# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown("## 📊 Data_Info")
st.sidebar.write(f"👤 **{st.session_state.user_name}**")
st.sidebar.write(f"🔑 Role : **{st.session_state.role}**")

st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "🏠 Dashboard",
        "📦 Distribution Numérique",
        "👤 Profil Client",
        "💰 Relevé Prix",
        "📝 Enquête",
        "📈 Statistiques"
    ]
)

if st.sidebar.button("🚪 Déconnexion", use_container_width=True):
    logout()


# =========================================================
# HEADER
# =========================================================
st.markdown(
    f"<div class='main-title'>📊 Data_Info</div>",
    unsafe_allow_html=True
)

st.caption(
    f"Utilisateur connecté : {st.session_state.user_name}"
)


# =========================================================
# DASHBOARD
# =========================================================
if menu == "🏠 Dashboard":

    st.header("🏠 Tableau de bord")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "POS",
        len(df_pos)
    )

    c2.metric(
        "Produits",
        len(df_products)
    )

    c3.metric(
        "Relevés prix",
        len(df_prices)
    )

    c4.metric(
        "Enquêtes",
        len(df_surveys)
    )

    st.markdown("---")

    st.subheader("📌 Modules Data_Info")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info(
            "**Distribution Numérique**\n\n"
            "Mesurer la présence des produits et des marques dans les POS."
        )

    with col2:
        st.info(
            "**Profil Client**\n\n"
            "Collecter les informations principales de chaque point de vente."
        )

    with col3:
        st.info(
            "**Relevé Prix**\n\n"
            "Collecter et comparer les prix du marché."
        )

    col4, col5 = st.columns(2)

    with col4:
        st.info(
            "**Enquête**\n\n"
            "Créer des enquêtes spécifiques sur le marché."
        )

    with col5:
        st.info(
            "**Statistiques**\n\n"
            "Suivre les KPI et l'évolution des données collectées."
        )


# =========================================================
# DISTRIBUTION NUMERIQUE
# =========================================================
elif menu == "📦 Distribution Numérique":

    st.header("📦 Distribution Numérique")

    if df_pos.empty:
        st.warning("La table POS est vide.")
        st.stop()

    if df_products.empty:
        st.warning("La table Produits est vide.")
        st.stop()

    with st.form("distribution_form"):

        st.subheader("📍 Point de vente")

        pos_names = []

        if "ID_POS" in df_pos.columns:
            pos_names = unique_sorted(df_pos, "ID_POS")

        selected_pos = st.selectbox(
            "POS",
            ["--- Sélectionner ---"] + pos_names
        )

        st.subheader("📦 Produit")

        marque_values = unique_sorted(df_products, "Marque")

        marque = st.selectbox(
            "Marque",
            ["--- Sélectionner ---"] + marque_values
        )

        temp = filter_products(
            df_products,
            marque="" if marque.startswith("---") else marque
        )

        categorie_values = unique_sorted(temp, "Catégorie")

        categorie = st.selectbox(
            "Catégorie",
            ["--- Sélectionner ---"] + categorie_values
        )

        temp = filter_products(
            df_products,
            marque="" if marque.startswith("---") else marque,
            categorie="" if categorie.startswith("---") else categorie
        )

        famille_values = unique_sorted(temp, "Famille")

        famille = st.selectbox(
            "Famille",
            ["--- Sélectionner ---"] + famille_values
        )

        temp = filter_products(
            df_products,
            marque="" if marque.startswith("---") else marque,
            categorie="" if categorie.startswith("---") else categorie,
            famille="" if famille.startswith("---") else famille
        )

        product_values = unique_sorted(temp, "Produit")

        produit = st.selectbox(
            "Produit",
            ["--- Sélectionner ---"] + product_values
        )

        temp = filter_products(
            df_products,
            marque="" if marque.startswith("---") else marque,
            categorie="" if categorie.startswith("---") else categorie,
            famille="" if famille.startswith("---") else famille,
            produit="" if produit.startswith("---") else produit
        )

        dimension_values = unique_sorted(
            temp,
            "Capacité_Dimension"
        )

        capacite = st.selectbox(
            "Capacité / Dimension",
            ["--- Sélectionner ---"] + dimension_values
        )

        col1, col2 = st.columns(2)

        with col1:
            quantite = st.number_input(
                "Quantité présente",
                min_value=0,
                step=1,
                value=0
            )

        with col2:
            date_visite = st.date_input(
                "Date de visite",
                value=datetime.now().date()
            )

        remarque = st.text_area("Remarque")

        save = st.form_submit_button(
            "💾 Enregistrer",
            use_container_width=True
        )

        if save:

            errors = []

            if selected_pos == "--- Sélectionner ---":
                errors.append("Sélectionnez un POS.")

            if marque == "--- Sélectionner ---":
                errors.append("Sélectionnez une marque.")

            if categorie == "--- Sélectionner ---":
                errors.append("Sélectionnez une catégorie.")

            if famille == "--- Sélectionner ---":
                errors.append("Sélectionnez une famille.")

            if produit == "--- Sélectionner ---":
                errors.append("Sélectionnez un produit.")

            if capacite == "--- Sélectionner ---":
                errors.append("Sélectionnez une capacité/dimension.")

            if errors:
                for error in errors:
                    st.error(error)
            else:

                append_row(
                    SHEET_DISTRIBUTION,
                    [
                        str(uuid.uuid4()),
                        str(date_visite),
                        selected_pos,
                        marque,
                        categorie,
                        famille,
                        produit,
                        capacite,
                        int(quantite),
                        st.session_state.user_id,
                        remarque
                    ]
                )

                st.success("✅ Distribution enregistrée.")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Derniers relevés")

    if not df_distribution.empty:
        st.dataframe(
            df_distribution.tail(20),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# PROFIL CLIENT
# =========================================================
elif menu == "👤 Profil Client":

    st.header("👤 Profil Client")

    if df_pos.empty:
        st.warning("La table POS est vide.")
        st.stop()

    pos_ids = unique_sorted(df_pos, "ID_POS")

    selected_pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"] + pos_ids
    )

    if selected_pos != "--- Sélectionner ---":

        existing = pd.DataFrame()

        if not df_profile.empty and "ID_POS" in df_profile.columns:
            existing = df_profile[
                df_profile["ID_POS"].astype(str).str.strip()
                == selected_pos
            ]

        with st.form("profile_form"):

            st.subheader("Informations du propriétaire")

            col1, col2 = st.columns(2)

            with col1:
                nom_proprietaire = st.text_input(
                    "Nom du propriétaire",
                    value=clean_text(
                        existing.iloc[-1].get("Nom_Proprietaire", "")
                        if not existing.empty else ""
                    )
                )

                contact_proprietaire = st.text_input(
                    "Contact propriétaire",
                    value=clean_text(
                        existing.iloc[-1].get("Contact_Proprietaire", "")
                        if not existing.empty else ""
                    )
                )

                nom_facade = st.text_input(
                    "Nom façade",
                    value=clean_text(
                        existing.iloc[-1].get("Nom_Facade", "")
                        if not existing.empty else ""
                    )
                )

                nom_acheteur = st.text_input(
                    "Nom acheteur",
                    value=clean_text(
                        existing.iloc[-1].get("Nom_Acheteur", "")
                        if not existing.empty else ""
                    )
                )

                contact_acheteur = st.text_input(
                    "Contact acheteur",
                    value=clean_text(
                        existing.iloc[-1].get("Contact_Acheteur", "")
                        if not existing.empty else ""
                    )
                )

            with col2:

                surface = st.number_input(
                    "Surface magasin (m²)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0
                )

                vitrines = st.number_input(
                    "Nombre de vitrines",
                    min_value=0,
                    step=1,
                    value=0
                )

                travailleurs = st.number_input(
                    "Nombre de travailleurs",
                    min_value=0,
                    step=1,
                    value=0
                )

                digital = st.selectbox(
                    "Présence digitale",
                    ["Oui", "Non"]
                )

                ca_2025 = st.number_input(
                    "Chiffre d'affaires 2025",
                    min_value=0.0,
                    step=1000.0,
                    value=0.0
                )

            remarque = st.text_area("Remarque")

            save_profile = st.form_submit_button(
                "💾 Enregistrer le profil",
                use_container_width=True
            )

            if save_profile:

                append_row(
                    SHEET_PROFILE,
                    [
                        str(uuid.uuid4()),
                        selected_pos,
                        str(datetime.now().date()),
                        nom_proprietaire,
                        contact_proprietaire,
                        nom_facade,
                        nom_acheteur,
                        contact_acheteur,
                        surface,
                        vitrines,
                        travailleurs,
                        digital == "Oui",
                        ca_2025,
                        remarque,
                        st.session_state.user_id
                    ]
                )

                st.success("✅ Profil client enregistré.")
                st.rerun()


# =========================================================
# RELEVE PRIX
# =========================================================
elif menu == "💰 Relevé Prix":

    st.header("💰 Relevé Prix")

    if df_pos.empty or df_products.empty:
        st.warning("Les tables POS et Produits doivent être renseignées.")
        st.stop()

    pos_values = unique_sorted(df_pos, "ID_POS")

    pos = st.selectbox(
        "POS",
        ["--- Sélectionner ---"] + pos_values
    )

    marque_values = unique_sorted(df_products, "Marque")

    marque = st.selectbox(
        "Marque",
        ["--- Sélectionner ---"] + marque_values
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque
    )

    categorie = st.selectbox(
        "Catégorie",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Catégorie")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie
    )

    famille = st.selectbox(
        "Famille",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Famille")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie,
        famille="" if famille.startswith("---") else famille
    )

    produit = st.selectbox(
        "Produit",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Produit")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie,
        famille="" if famille.startswith("---") else famille,
        produit="" if produit.startswith("---") else produit
    )

    capacite = st.selectbox(
        "Capacité / Dimension",
        ["--- Sélectionner ---"]
        + unique_sorted(temp, "Capacité_Dimension")
    )

    col1, col2 = st.columns(2)

    with col1:
        prix = st.number_input(
            "Prix de vente",
            min_value=0.0,
            step=100.0
        )

    with col2:
        promo = st.selectbox(
            "En promotion ?",
            ["Non", "Oui"]
        )

    prix_promo = st.number_input(
        "Prix promotionnel",
        min_value=0.0,
        step=100.0
    )

    date_releve = st.date_input(
        "Date du relevé",
        value=datetime.now().date()
    )

    remarque = st.text_area("Remarque")

    if st.button(
        "💾 Enregistrer le prix",
        use_container_width=True
    ):

        errors = []

        if pos == "--- Sélectionner ---":
            errors.append("Sélectionnez un POS.")

        if marque == "--- Sélectionner ---":
            errors.append("Sélectionnez une marque.")

        if categorie == "--- Sélectionner ---":
            errors.append("Sélectionnez une catégorie.")

        if famille == "--- Sélectionner ---":
            errors.append("Sélectionnez une famille.")

        if produit == "--- Sélectionner ---":
            errors.append("Sélectionnez un produit.")

        if capacite == "--- Sélectionner ---":
            errors.append("Sélectionnez une capacité/dimension.")

        if prix <= 0:
            errors.append("Le prix doit être supérieur à 0.")

        if errors:
            for error in errors:
                st.error(error)
        else:

            append_row(
                SHEET_PRICES,
                [
                    str(uuid.uuid4()),
                    str(date_releve),
                    pos,
                    marque,
                    categorie,
                    famille,
                    produit,
                    capacite,
                    prix,
                    prix_promo if promo == "Oui" else 0,
                    promo == "Oui",
                    remarque,
                    st.session_state.user_id
                ]
            )

            st.success("✅ Relevé prix enregistré.")
            st.rerun()


# =========================================================
# ENQUETE
# =========================================================
elif menu == "📝 Enquête":

    st.header("📝 Enquête")

    if df_pos.empty or df_products.empty:
        st.warning("Les tables POS et Produits doivent être renseignées.")
        st.stop()

    if df_subjects.empty:
        st.warning(
            "Aucun sujet d'enquête disponible. "
            "Ajoutez d'abord des lignes dans Enquetes_Sujets."
        )
        st.stop()

    subject_values = unique_sorted(df_subjects, "Nom_Enquete")

    sujet = st.selectbox(
        "Sujet de l'enquête",
        ["--- Sélectionner ---"] + subject_values
    )

    pos_values = unique_sorted(df_pos, "ID_POS")

    pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"] + pos_values
    )

    st.subheader("Produit observé")

    marque_exposee = st.text_input(
        "Marque exposée"
    )

    marque = st.selectbox(
        "Marque du produit",
        ["--- Sélectionner ---"] + unique_sorted(df_products, "Marque")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque
    )

    categorie = st.selectbox(
        "Catégorie",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Catégorie")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie
    )

    famille = st.selectbox(
        "Famille",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Famille")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie,
        famille="" if famille.startswith("---") else famille
    )

    produit = st.selectbox(
        "Produit",
        ["--- Sélectionner ---"] + unique_sorted(temp, "Produit")
    )

    temp = filter_products(
        df_products,
        marque="" if marque.startswith("---") else marque,
        categorie="" if categorie.startswith("---") else categorie,
        famille="" if famille.startswith("---") else famille,
        produit="" if produit.startswith("---") else produit
    )

    capacite = st.selectbox(
        "Capacité / Dimension",
        ["--- Sélectionner ---"]
        + unique_sorted(temp, "Capacité_Dimension")
    )

    col1, col2 = st.columns(2)

    with col1:
        prix = st.number_input(
            "Prix",
            min_value=0.0,
            step=100.0
        )

        stock = st.selectbox(
            "Stock disponible ?",
            ["Oui", "Non"]
        )

    with col2:
        promo = st.selectbox(
            "En promotion ?",
            ["Oui", "Non"]
        )

        frequence = st.number_input(
            "Fréquence de vente / jour",
            min_value=0.0,
            step=1.0
        )

    remarque = st.text_area("Remarque")

    if st.button(
        "💾 Enregistrer l'enquête",
        use_container_width=True
    ):

        errors = []

        if sujet == "--- Sélectionner ---":
            errors.append("Sélectionnez le sujet de l'enquête.")

        if pos == "--- Sélectionner ---":
            errors.append("Sélectionnez le POS.")

        if marque == "--- Sélectionner ---":
            errors.append("Sélectionnez une marque.")

        if categorie == "--- Sélectionner ---":
            errors.append("Sélectionnez une catégorie.")

        if famille == "--- Sélectionner ---":
            errors.append("Sélectionnez une famille.")

        if produit == "--- Sélectionner ---":
            errors.append("Sélectionnez un produit.")

        if capacite == "--- Sélectionner ---":
            errors.append("Sélectionnez une capacité/dimension.")

        if errors:
            for error in errors:
                st.error(error)
        else:

            append_row(
                SHEET_SURVEYS,
                [
                    str(uuid.uuid4()),
                    str(datetime.now().date()),
                    sujet,
                    pos,
                    marque_exposee,
                    marque,
                    categorie,
                    famille,
                    produit,
                    capacite,
                    prix,
                    stock == "Oui",
                    promo == "Oui",
                    frequence,
                    remarque,
                    st.session_state.user_id
                ]
            )

            st.success("✅ Enquête enregistrée.")
            st.rerun()


# =========================================================
# STATISTIQUES
# =========================================================
elif menu == "📈 Statistiques":

    st.header("📈 Statistiques")

    # -----------------------------------------------------
    # KPI
    # -----------------------------------------------------
    total_pos = len(df_pos)

    total_distribution = len(df_distribution)

    total_price = len(df_prices)

    total_surveys = len(df_surveys)

    total_brands = (
        df_products["Marque"].nunique()
        if not df_products.empty and "Marque" in df_products.columns
        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("POS", total_pos)
    c2.metric("Relevés distribution", total_distribution)
    c3.metric("Relevés prix", total_price)
    c4.metric("Enquêtes", total_surveys)
    c5.metric("Marques", total_brands)

    st.markdown("---")

    # -----------------------------------------------------
    # DISTRIBUTION PAR MARQUE
    # -----------------------------------------------------
    if not df_distribution.empty:

        st.subheader("📦 Distribution par marque")

        if "Marque" in df_distribution.columns:

            dist = df_distribution.copy()

            if "Quantite" in dist.columns:
                dist["Quantite"] = pd.to_numeric(
                    dist["Quantite"],
                    errors="coerce"
                ).fillna(0)

                chart = (
                    dist.groupby("Marque")["Quantite"]
                    .sum()
                    .sort_values(ascending=False)
                )

                st.bar_chart(chart)

        st.subheader("🏷️ Distribution par catégorie")

        if "Catégorie" in df_distribution.columns:

            if "Quantite" in df_distribution.columns:

                chart_cat = (
                    dist.groupby("Catégorie")["Quantite"]
                    .sum()
                    .sort_values(ascending=False)
                )

                st.bar_chart(chart_cat)

    # -----------------------------------------------------
    # PRIX
    # -----------------------------------------------------
    if not df_prices.empty:

        st.subheader("💰 Analyse des prix")

        if "Prix_Vente" in df_prices.columns:

            price_df = df_prices.copy()

            price_df["Prix_Vente"] = pd.to_numeric(
                price_df["Prix_Vente"],
                errors="coerce"
            )

            if "Marque" in price_df.columns:

                avg_price = (
                    price_df.groupby("Marque")["Prix_Vente"]
                    .mean()
                    .sort_values(ascending=False)
                )

                st.bar_chart(avg_price)

        if all(
            c in price_df.columns
            for c in ["Marque", "Prix_Vente"]
        ):
            price_summary = (
                price_df.groupby("Marque")
                .agg(
                    Prix_Moyen=("Prix_Vente", "mean"),
                    Prix_Min=("Prix_Vente", "min"),
                    Prix_Max=("Prix_Vente", "max"),
                    Nb_Releves=("Prix_Vente", "count")
                )
                .reset_index()
                .sort_values("Prix_Moyen", ascending=False)
            )

            st.dataframe(
                price_summary,
                use_container_width=True,
                hide_index=True
            )

    # -----------------------------------------------------
    # ENQUETES
    # -----------------------------------------------------
    if not df_surveys.empty:

        st.subheader("📝 Résultats des enquêtes")

        if "Marque" in df_surveys.columns:

            survey_brand = (
                df_surveys["Marque"]
                .astype(str)
                .value_counts()
            )

            st.bar_chart(survey_brand)

        if "Frequence_Vente_Jour" in df_surveys.columns:

            freq_df = df_surveys.copy()

            freq_df["Frequence_Vente_Jour"] = pd.to_numeric(
                freq_df["Frequence_Vente_Jour"],
                errors="coerce"
            )

            if "Marque" in freq_df.columns:

                avg_freq = (
                    freq_df.groupby("Marque")[
                        "Frequence_Vente_Jour"
                    ]
                    .mean()
                    .sort_values(ascending=False)
                )

                st.subheader("📊 Fréquence moyenne de vente / jour")
                st.bar_chart(avg_freq)

    # -----------------------------------------------------
    # TABLES
    # -----------------------------------------------------
    st.markdown("---")
    st.subheader("📋 Données disponibles")

    tabs = st.tabs([
        "Distribution",
        "Prix",
        "Enquêtes",
        "Profils"
    ])

    with tabs[0]:
        if not df_distribution.empty:
            st.dataframe(
                df_distribution,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune donnée.")

    with tabs[1]:
        if not df_prices.empty:
            st.dataframe(
                df_prices,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune donnée.")

    with tabs[2]:
        if not df_surveys.empty:
            st.dataframe(
                df_surveys,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune donnée.")

    with tabs[3]:
        if not df_profile.empty:
            st.dataframe(
                df_profile,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucune donnée.")
