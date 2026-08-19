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

SHEET_MATERIAL_TYPES = "Types_Materiel"
SHEET_MATERIAL_POS = "Materiel_POS"
SHEET_MATERIAL_CONTROL = "Controle_Materiel"


@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["google"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)


client = get_client()


def get_spreadsheet():
    """Ouvre le fichier Google Sheets et retourne une erreur lisible."""
    try:
        return client.open_by_key(SPREADSHEET_ID)
    except gspread.exceptions.APIError as e:
        st.error(
            "❌ Impossible d'accéder au Google Sheet.\n\n"
            "Vérifiez les points suivants :\n"
            "1. Le SPREADSHEET_ID est correct.\n"
            "2. Le fichier Google Sheets est partagé avec le compte de service présent dans st.secrets['google'].\n"
            "3. Le compte de service dispose du droit Éditeur.\n\n"
            f"Détail Google API : {e}"
        )
        raise
    except Exception as e:
        st.error(
            "❌ Erreur lors de l'ouverture du Google Sheet :\n\n"
            f"{e}"
        )
        raise


def get_ws(sheet_name):
    """Retourne une feuille et signale clairement si son nom est incorrect."""
    spreadsheet = get_spreadsheet()

    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        available = [ws.title for ws in spreadsheet.worksheets()]
        st.error(
            f"❌ La feuille '{sheet_name}' n'existe pas dans le fichier Google Sheets.\n\n"
            f"Feuilles disponibles : {', '.join(available)}"
        )
        raise
    except gspread.exceptions.APIError as e:
        st.error(
            f"❌ Google Sheets a refusé l'accès à la feuille '{sheet_name}'.\n\n"
            f"Détail Google API : {e}\n\n"
            "Vérifiez le partage du fichier avec le compte de service."
        )
        raise


@st.cache_data(ttl=30)
def load_sheet(sheet_name):
    """Charge une feuille Google Sheets."""
    ws = get_ws(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)

    if not df.empty:
        df.columns = (
            df.columns.astype(str)
            .str.strip()
        )

    return df


def append_row(sheet_name, row):
    """Ajoute une ligne dans une feuille Google Sheets."""
    try:
        ws = get_ws(sheet_name)
        ws.append_row(
            row,
            value_input_option="USER_ENTERED"
        )
        load_sheet.clear()
    except gspread.exceptions.APIError as e:
        st.error(
            f"❌ Erreur Google Sheets lors de l'enregistrement dans '{sheet_name}'.\n\n"
            f"Détail : {e}\n\n"
            "Si l'erreur est [403], partagez le Google Sheet avec le compte de service en Éditeur. "
            "Si l'erreur est [404], vérifiez le SPREADSHEET_ID et le nom de la feuille."
        )
        raise


def append_dict_row(sheet_name, data):
    """
    Ajoute une ligne à partir d'un dictionnaire
    en respectant l'ordre des colonnes existantes.
    """
    ws = get_ws(sheet_name)

    headers = [
        str(x).strip()
        for x in ws.row_values(1)
    ]

    row = [
        data.get(header, "")
        for header in headers
    ]

    ws.append_row(
        row,
        value_input_option="USER_ENTERED"
    )

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
        .fillna("")
        .astype(str)
        .str.strip()
    )

    values = [
        v for v in values.unique().tolist()
        if v
    ]

    return sorted(values)


# =========================================================
# FILTRE PRODUITS
# =========================================================
def filter_products(
    products,
    marque="",
    categorie="",
    famille="",
    produit=""
):
    """
    Filtre en cascade :
    Marque
    -> Catégorie
    -> Famille
    -> Produit
    """

    if products.empty:
        return products.copy()

    result = products.copy()

    # Nettoyage des colonnes
    for col in [
        "Marque",
        "Catégorie",
        "Famille",
        "Produit",
        "Capacité_Dimension"
    ]:
        if col in result.columns:
            result[col] = (
                result[col]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    if marque:
        result = result[
            result["Marque"].str.lower()
            == str(marque).strip().lower()
        ]

    if categorie:
        result = result[
            result["Catégorie"].str.lower()
            == str(categorie).strip().lower()
        ]

    if famille:
        result = result[
            result["Famille"].str.lower()
            == str(famille).strip().lower()
        ]

    if produit:
        result = result[
            result["Produit"].str.lower()
            == str(produit).strip().lower()
        ]

    return result


# =========================================================
# SELECTEUR PRODUIT EN CASCADE
# =========================================================
def product_selector(prefix="product"):
    """
    Cascade dynamique :

    Marque
        ↓
    Catégorie
        ↓
    Famille
        ↓
    Produit
        ↓
    Capacité / Dimension
    """

    # -----------------------------------------------------
    # MARQUE
    # -----------------------------------------------------
    marque_values = unique_sorted(
        df_products,
        "Marque"
    )

    marque = st.selectbox(
        "Marque",
        ["--- Sélectionner ---"] + marque_values,
        key=f"{prefix}_marque"
    )

    # -----------------------------------------------------
    # CATEGORIE
    # -----------------------------------------------------
    temp = filter_products(
        df_products,
        marque="" if marque == "--- Sélectionner ---"
        else marque
    )

    categorie_values = unique_sorted(
        temp,
        "Catégorie"
    )

    categorie = st.selectbox(
        "Catégorie",
        ["--- Sélectionner ---"] + categorie_values,
        key=f"{prefix}_categorie"
    )

    # -----------------------------------------------------
    # FAMILLE
    # -----------------------------------------------------
    temp = filter_products(
        df_products,
        marque="" if marque == "--- Sélectionner ---"
        else marque,
        categorie="" if categorie == "--- Sélectionner ---"
        else categorie
    )

    famille_values = unique_sorted(
        temp,
        "Famille"
    )

    famille = st.selectbox(
        "Famille",
        ["--- Sélectionner ---"] + famille_values,
        key=f"{prefix}_famille"
    )

    # -----------------------------------------------------
    # PRODUIT
    # -----------------------------------------------------
    temp = filter_products(
        df_products,
        marque="" if marque == "--- Sélectionner ---"
        else marque,
        categorie="" if categorie == "--- Sélectionner ---"
        else categorie,
        famille="" if famille == "--- Sélectionner ---"
        else famille
    )

    produit_values = unique_sorted(
        temp,
        "Produit"
    )

    produit = st.selectbox(
        "Produit",
        ["--- Sélectionner ---"] + produit_values,
        key=f"{prefix}_produit"
    )

    # -----------------------------------------------------
    # CAPACITE / DIMENSION
    # -----------------------------------------------------
    temp = filter_products(
        df_products,
        marque="" if marque == "--- Sélectionner ---"
        else marque,
        categorie="" if categorie == "--- Sélectionner ---"
        else categorie,
        famille="" if famille == "--- Sélectionner ---"
        else famille,
        produit="" if produit == "--- Sélectionner ---"
        else produit
    )

    dimension_values = unique_sorted(
        temp,
        "Capacité_Dimension"
    )

    capacite = st.selectbox(
        "Capacité / Dimension",
        ["--- Sélectionner ---"] + dimension_values,
        key=f"{prefix}_capacite"
    )

    return (
        marque,
        categorie,
        famille,
        produit,
        capacite
    )


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

    users["Nom"] = (
        users["Nom"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    active_users = users.copy()

    if "Statut" in active_users.columns:
        active_users = active_users[
            active_users["Statut"]
            .astype(str)
            .str.lower()
            .str.strip()
            != "inactif"
        ]

    names = sorted(
        active_users["Nom"]
        .dropna()
        .unique()
        .tolist()
    )

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

                st.error(
                    "Utilisateur introuvable."
                )

            else:

                user = user.iloc[0]

                if clean_text(
                    user["Password"]
                ) != password.strip():

                    st.error(
                        "Mot de passe incorrect."
                    )

                else:

                    st.session_state.logged_in = True

                    st.session_state.user_name = clean_text(
                        user["Nom"]
                    )

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
df_material_types = load_sheet(SHEET_MATERIAL_TYPES)
df_material_pos = load_sheet(SHEET_MATERIAL_POS)
df_material_control = load_sheet(SHEET_MATERIAL_CONTROL)


# =========================================================
# SIDEBAR
# =========================================================
st.sidebar.markdown("## 📊 Data_Info")
st.sidebar.write(
    f"👤 **{st.session_state.user_name}**"
)
st.sidebar.write(
    f"🔑 Role : **{st.session_state.role}**"
)

st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    [
        "🏠 Dashboard",
        "📦 Distribution Numérique",
        "👤 Profil Client",
        "💰 Relevé Prix",
        "📝 Enquête",
        "🧰 Matériel POS",
        "🚗 Visites POS",
        "🎯 Objectifs POS",
        "📈 Statistiques"
    ]
)

if st.sidebar.button(
    "🚪 Déconnexion",
    use_container_width=True
):
    logout()


# =========================================================
# HEADER
# =========================================================
st.markdown(
    "<div class='main-title'>📊 Data_Info</div>",
    unsafe_allow_html=True
)

st.caption(
    f"Utilisateur connecté : "
    f"{st.session_state.user_name}"
)


# =========================================================
# DASHBOARD
# =========================================================
if menu == "🏠 Dashboard":

    st.header("🏠 Tableau de bord")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("POS", len(df_pos))
    c2.metric("Produits", len(df_products))
    c3.metric("Relevés prix", len(df_prices))
    c4.metric("Enquêtes", len(df_surveys))

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

    st.subheader("📍 Point de vente")

    pos_names = unique_sorted(
        df_pos,
        "ID_POS"
    )

    selected_pos = st.selectbox(
        "POS",
        ["--- Sélectionner ---"] + pos_names,
        key="distribution_pos"
    )

    st.markdown("---")

    st.subheader("📦 Produit")

    marque, categorie, famille, produit, capacite = product_selector(
        prefix="distribution"
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        quantite = st.number_input(
            "Quantité présente",
            min_value=0,
            step=1,
            value=0,
            key="distribution_quantite"
        )

    with col2:
        date_visite = st.date_input(
            "Date de visite",
            value=datetime.now().date(),
            key="distribution_date"
        )

    remarque = st.text_area(
        "Remarque",
        key="distribution_remarque"
    )

    if st.button(
        "💾 Enregistrer",
        use_container_width=True,
        key="distribution_save"
    ):

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
            errors.append(
                "Sélectionnez une capacité/dimension."
            )

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

            st.success(
                "✅ Distribution enregistrée."
            )

            st.rerun()

    st.markdown("---")
    st.subheader("📋 Derniers relevés")

    if not df_distribution.empty:

        st.dataframe(
            df_distribution.tail(20),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucun relevé de distribution enregistré."
        )


# =========================================================
# PROFIL CLIENT
# =========================================================
elif menu == "👤 Profil Client":

    st.header("👤 Profil Client")

    st.info(
        "Si le POS existe, sélectionnez-le pour consulter/modifier son profil. "
        "Sinon, créez d'abord un nouveau POS puis renseignez son profil."
    )

    tab_existing, tab_new = st.tabs(
        ["🔎 POS existant", "➕ Nouveau POS"]
    )

    # -----------------------------------------------------
    # POS EXISTANT
    # -----------------------------------------------------
    with tab_existing:

        if df_pos.empty:

            st.warning(
                "La table POS est vide."
            )

        else:

            selected_pos = st.selectbox(
                "Point de vente",
                ["--- Sélectionner ---"]
                + unique_sorted(df_pos, "ID_POS"),
                key="profile_existing_pos"
            )

            if selected_pos != "--- Sélectionner ---":

                existing = pd.DataFrame()

                if (
                    not df_profile.empty
                    and "ID_POS" in df_profile.columns
                ):
                    existing = df_profile[
                        df_profile["ID_POS"]
                        .astype(str)
                        .str.strip()
                        == selected_pos
                    ]

                pos_row = df_pos[
                    df_pos["ID_POS"]
                    .astype(str)
                    .str.strip()
                    == selected_pos
                ]

                pos_row = (
                    pos_row.iloc[-1]
                    if not pos_row.empty
                    else None
                )

                profile = (
                    existing.iloc[-1]
                    if not existing.empty
                    else None
                )

                if profile is not None:
                    st.success(
                        "✅ Profil existant trouvé. "
                        "Les informations sont préremplies."
                    )
                else:
                    st.info(
                        "ℹ️ Le POS existe mais son profil détaillé "
                        "n'est pas encore renseigné."
                    )

                with st.form("profile_form"):

                    st.subheader(
                        "🏪 Informations du POS"
                    )

                    c1, c2 = st.columns(2)

                    with c1:

                        nom_pos = st.text_input(
                            "Nom POS",
                            value=clean_text(
                                pos_row.get(
                                    "Nom_POS",
                                    pos_row.get("Nom", "")
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        wilaya = st.text_input(
                            "Wilaya",
                            value=clean_text(
                                pos_row.get("Wilaya", "")
                                if pos_row is not None
                                else ""
                            )
                        )

                        commune = st.text_input(
                            "Commune",
                            value=clean_text(
                                pos_row.get("Commune", "")
                                if pos_row is not None
                                else ""
                            )
                        )

                        adresse = st.text_area(
                            "Adresse",
                            value=clean_text(
                                pos_row.get("Adresse", "")
                                if pos_row is not None
                                else ""
                            )
                        )

                    with c2:

                        telephone = st.text_input(
                            "Téléphone",
                            value=clean_text(
                                pos_row.get(
                                    "Telephone",
                                    pos_row.get("Téléphone", "")
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        email = st.text_input(
                            "Email",
                            value=clean_text(
                                pos_row.get("Email", "")
                                if pos_row is not None
                                else ""
                            )
                        )

                        statut_value = clean_text(
                            pos_row.get(
                                "Statut",
                                "Actif"
                            )
                            if pos_row is not None
                            else "Actif"
                        )

                        statut = st.selectbox(
                            "Statut",
                            ["Actif", "Inactif"],
                            index=(
                                1
                                if statut_value.lower()
                                == "inactif"
                                else 0
                            )
                        )

                    st.subheader(
                        "👤 Informations client"
                    )

                    c1, c2 = st.columns(2)

                    with c1:

                        nom_proprietaire = st.text_input(
                            "Nom du propriétaire",
                            value=clean_text(
                                profile.get(
                                    "Nom_Proprietaire",
                                    ""
                                )
                                if profile is not None
                                else ""
                            )
                        )

                        contact_proprietaire = st.text_input(
                            "Contact propriétaire",
                            value=clean_text(
                                profile.get(
                                    "Contact_Proprietaire",
                                    ""
                                )
                                if profile is not None
                                else ""
                            )
                        )

                        nom_facade = st.text_input(
                            "Nom façade",
                            value=clean_text(
                                profile.get(
                                    "Nom_Facade",
                                    ""
                                )
                                if profile is not None
                                else ""
                            )
                        )

                        nom_acheteur = st.text_input(
                            "Nom acheteur",
                            value=clean_text(
                                profile.get(
                                    "Nom_Acheteur",
                                    ""
                                )
                                if profile is not None
                                else ""
                            )
                        )

                        contact_acheteur = st.text_input(
                            "Contact acheteur",
                            value=clean_text(
                                profile.get(
                                    "Contact_Acheteur",
                                    ""
                                )
                                if profile is not None
                                else ""
                            )
                        )

                    with c2:

                        surface = st.number_input(
                            "Surface magasin (m²)",
                            min_value=0.0,
                            step=1.0,
                            value=float(
                                profile.get(
                                    "Surface_Magasin",
                                    0
                                )
                                or 0
                            )
                            if profile is not None
                            else 0.0
                        )

                        surface_expo = st.number_input(
                            "Surface exposition (m²)",
                            min_value=0.0,
                            step=1.0,
                            value=float(
                                profile.get(
                                    "Surface_Exposition",
                                    0
                                )
                                or 0
                            )
                            if profile is not None
                            else 0.0
                        )

                        vitrines = st.number_input(
                            "Nombre de vitrines",
                            min_value=0,
                            step=1,
                            value=int(
                                float(
                                    profile.get(
                                        "Nombre_Vitrines",
                                        0
                                    )
                                    or 0
                                )
                            )
                            if profile is not None
                            else 0
                        )

                        travailleurs = st.number_input(
                            "Nombre de travailleurs",
                            min_value=0,
                            step=1,
                            value=int(
                                float(
                                    profile.get(
                                        "Nombre_Travailleurs",
                                        0
                                    )
                                    or 0
                                )
                            )
                            if profile is not None
                            else 0
                        )

                        digital_value = clean_text(
                            profile.get(
                                "Presence_Digitale",
                                "Non"
                            )
                            if profile is not None
                            else "Non"
                        )

                        digital = st.selectbox(
                            "Présence digitale",
                            ["Oui", "Non"],
                            index=(
                                0
                                if digital_value.lower()
                                in ["oui", "true", "1"]
                                else 1
                            )
                        )

                        ca_2025 = st.number_input(
                            "Chiffre d'affaires 2025",
                            min_value=0.0,
                            step=1000.0,
                            value=float(
                                profile.get(
                                    "CA_2025",
                                    0
                                )
                                or 0
                            )
                            if profile is not None
                            else 0.0
                        )

                    observation = st.text_area(
                        "Observation",
                        value=clean_text(
                            profile.get(
                                "Observation",
                                profile.get(
                                    "Remarque",
                                    ""
                                )
                            )
                            if profile is not None
                            else ""
                        )
                    )

                    save_profile = st.form_submit_button(
                        "💾 Enregistrer le profil",
                        use_container_width=True
                    )

                if save_profile:

                    ws = get_ws(SHEET_POS)

                    headers = [
                        str(x).strip()
                        for x in ws.row_values(1)
                    ]

                    records = ws.get_all_records()

                    found = False

                    for idx, row in enumerate(
                        records,
                        start=2
                    ):

                        if clean_text(
                            row.get("ID_POS", "")
                        ) == selected_pos:

                            values = dict(row)

                            aliases = {
                                "Nom_POS": nom_pos,
                                "Nom": nom_pos,
                                "Wilaya": wilaya,
                                "Commune": commune,
                                "Adresse": adresse,
                                "Telephone": telephone,
                                "Téléphone": telephone,
                                "Email": email,
                                "Statut": statut
                            }

                            values.update(aliases)

                            newrow = [
                                values.get(
                                    h,
                                    ""
                                )
                                for h in headers
                            ]

                            if len(headers) <= 26:

                                end_col = (
                                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                    [len(headers) - 1]
                                )

                                ws.update(
                                    f"A{idx}:{end_col}{idx}",
                                    [newrow]
                                )

                            else:

                                ws.update(
                                    f"A{idx}",
                                    [newrow]
                                )

                            found = True
                            break

                    if not found:

                        append_dict_row(
                            SHEET_POS,
                            {
                                "ID_POS": selected_pos,
                                "Nom_POS": nom_pos,
                                "Nom": nom_pos,
                                "Wilaya": wilaya,
                                "Commune": commune,
                                "Adresse": adresse,
                                "Telephone": telephone,
                                "Téléphone": telephone,
                                "Email": email,
                                "Statut": statut
                            }
                        )

                    append_dict_row(
                        SHEET_PROFILE,
                        {
                            "ID_Profil": str(uuid.uuid4()),
                            "ID": str(uuid.uuid4()),
                            "ID_POS": selected_pos,
                            "Date": str(datetime.now().date()),
                            "Date_Mise_A_Jour": str(datetime.now()),
                            "Nom_Proprietaire": nom_proprietaire,
                            "Proprietaire": nom_proprietaire,
                            "Contact_Proprietaire": contact_proprietaire,
                            "Nom_Facade": nom_facade,
                            "Nom_Acheteur": nom_acheteur,
                            "Acheteur": nom_acheteur,
                            "Contact_Acheteur": contact_acheteur,
                            "Surface_Magasin": surface,
                            "Surface": surface,
                            "Surface_Exposition": surface_expo,
                            "Nombre_Vitrines": vitrines,
                            "Vitrines": vitrines,
                            "Nombre_Travailleurs": travailleurs,
                            "Travailleurs": travailleurs,
                            "Presence_Digitale": digital == "Oui",
                            "Présence_Digitale": digital == "Oui",
                            "CA_2025": ca_2025,
                            "Observation": observation,
                            "Remarque": observation,
                            "ID_User": st.session_state.user_id
                        }
                    )

                    st.success(
                        "✅ Profil enregistré avec succès."
                    )

                    load_sheet.clear()
                    st.rerun()

    # -----------------------------------------------------
    # NOUVEAU POS
    # -----------------------------------------------------
    with tab_new:

        with st.form("new_pos_form"):

            st.subheader("➕ Nouveau POS")

            c1, c2 = st.columns(2)

            with c1:

                new_id = st.text_input(
                    "ID_POS *",
                    value=(
                        "POS-"
                        + str(uuid.uuid4())[:8].upper()
                    )
                )

                new_nom = st.text_input(
                    "Nom POS *"
                )

                new_wilaya = st.text_input(
                    "Wilaya *"
                )

                new_commune = st.text_input(
                    "Commune *"
                )

            with c2:

                new_adresse = st.text_area(
                    "Adresse"
                )

                new_tel = st.text_input(
                    "Téléphone"
                )

                new_email = st.text_input(
                    "Email"
                )

                new_statut = st.selectbox(
                    "Statut",
                    ["Actif", "Inactif"]
                )

            st.subheader(
                "👤 Profil client"
            )

            c1, c2 = st.columns(2)

            with c1:

                p_nom = st.text_input(
                    "Nom du propriétaire"
                )

                p_contact = st.text_input(
                    "Contact propriétaire"
                )

                p_facade = st.text_input(
                    "Nom façade"
                )

                p_acheteur = st.text_input(
                    "Nom acheteur"
                )

                p_acheteur_contact = st.text_input(
                    "Contact acheteur"
                )

            with c2:

                p_surface = st.number_input(
                    "Surface magasin (m²)",
                    min_value=0.0,
                    step=1.0
                )

                p_expo = st.number_input(
                    "Surface exposition (m²)",
                    min_value=0.0,
                    step=1.0
                )

                p_vitrines = st.number_input(
                    "Nombre de vitrines",
                    min_value=0,
                    step=1
                )

                p_workers = st.number_input(
                    "Nombre de travailleurs",
                    min_value=0,
                    step=1
                )

                p_digital = st.selectbox(
                    "Présence digitale",
                    ["Oui", "Non"]
                )

                p_ca = st.number_input(
                    "Chiffre d'affaires 2025",
                    min_value=0.0,
                    step=1000.0
                )

            p_obs = st.text_area(
                "Observation"
            )

            create = st.form_submit_button(
                "💾 Enregistrer le nouveau POS et son profil",
                use_container_width=True
            )

        if create:

            errors = []

            if not new_id.strip():
                errors.append(
                    "ID_POS obligatoire."
                )

            if not new_nom.strip():
                errors.append(
                    "Nom POS obligatoire."
                )

            if not new_wilaya.strip():
                errors.append(
                    "Wilaya obligatoire."
                )

            if not new_commune.strip():
                errors.append(
                    "Commune obligatoire."
                )

            if new_id.strip() in unique_sorted(
                df_pos,
                "ID_POS"
            ):
                errors.append(
                    "Cet ID_POS existe déjà."
                )

            if errors:

                for e in errors:
                    st.error(e)

            else:

                append_dict_row(
                    SHEET_POS,
                    {
                        "ID_POS": new_id.strip(),
                        "Nom_POS": new_nom.strip(),
                        "Nom": new_nom.strip(),
                        "Wilaya": new_wilaya,
                        "Commune": new_commune,
                        "Adresse": new_adresse,
                        "Telephone": new_tel,
                        "Téléphone": new_tel,
                        "Email": new_email,
                        "Statut": new_statut,
                        "Date_Creation": str(
                            datetime.now().date()
                        )
                    }
                )

                append_dict_row(
                    SHEET_PROFILE,
                    {
                        "ID_Profil": str(uuid.uuid4()),
                        "ID": str(uuid.uuid4()),
                        "ID_POS": new_id.strip(),
                        "Date": str(datetime.now().date()),
                        "Date_Mise_A_Jour": str(datetime.now()),
                        "Nom_Proprietaire": p_nom,
                        "Proprietaire": p_nom,
                        "Contact_Proprietaire": p_contact,
                        "Nom_Facade": p_facade,
                        "Nom_Acheteur": p_acheteur,
                        "Acheteur": p_acheteur,
                        "Contact_Acheteur": p_acheteur_contact,
                        "Surface_Magasin": p_surface,
                        "Surface": p_surface,
                        "Surface_Exposition": p_expo,
                        "Nombre_Vitrines": p_vitrines,
                        "Vitrines": p_vitrines,
                        "Nombre_Travailleurs": p_workers,
                        "Travailleurs": p_workers,
                        "Presence_Digitale": p_digital == "Oui",
                        "Présence_Digitale": p_digital == "Oui",
                        "CA_2025": p_ca,
                        "Observation": p_obs,
                        "Remarque": p_obs,
                        "ID_User": st.session_state.user_id
                    }
                )

                st.success(
                    "✅ Nouveau POS et profil enregistrés."
                )

                load_sheet.clear()
                st.rerun()


# =========================================================
# MATERIEL POS
# =========================================================
elif menu == "🧰 Matériel POS":

    st.header(
        "🧰 Gestion du matériel installé dans les POS"
    )

    st.info(
        "Suivi des tinda, logos, présentoirs, racks, "
        "vitrines, posters, affichage et autres matériels."
    )

    tab_add, tab_control, tab_history = st.tabs(
        [
            "➕ Installer / enregistrer",
            "🔎 Contrôler",
            "📋 Historique"
        ]
    )

    # -----------------------------------------------------
    # AJOUT
    # -----------------------------------------------------
    with tab_add:

        if df_pos.empty:

            st.warning(
                "La table POS est vide."
            )

        elif df_material_types.empty:

            st.warning(
                "La table Types_Materiel est vide. "
                "Créez d'abord les types de matériel."
            )

        else:

            pos = st.selectbox(
                "Point de vente",
                ["--- Sélectionner ---"]
                + unique_sorted(df_pos, "ID_POS"),
                key="mat_pos"
            )

            type_mat = st.selectbox(
                "Type de matériel",
                ["--- Sélectionner ---"]
                + unique_sorted(
                    df_material_types,
                    "Type_Materiel"
                ),
                key="mat_type"
            )

            type_row = None

            if type_mat != "--- Sélectionner ---":

                tmp = df_material_types[
                    df_material_types[
                        "Type_Materiel"
                    ]
                    .astype(str)
                    .str.strip()
                    == type_mat
                ]

                if not tmp.empty:
                    type_row = tmp.iloc[-1]

            categorie_mat = clean_text(
                type_row.get(
                    "Categorie_Materiel",
                    type_row.get(
                        "Catégorie_Materiel",
                        ""
                    )
                )
                if type_row is not None
                else ""
            )

            if categorie_mat:
                st.caption(
                    f"Catégorie : **{categorie_mat}**"
                )

            c1, c2 = st.columns(2)

            with c1:

                marque_mat = st.selectbox(
                    "Marque du matériel",
                    ["--- Sélectionner ---"]
                    + unique_sorted(
                        df_products,
                        "Marque"
                    ),
                    key="mat_brand"
                )

                reference = st.text_input(
                    "Référence matériel"
                )

                quantite = st.number_input(
                    "Quantité",
                    min_value=1,
                    value=1,
                    step=1
                )

            with c2:

                date_install = st.date_input(
                    "Date d'installation",
                    value=datetime.now().date()
                )

                etat = st.selectbox(
                    "État",
                    [
                        "Neuf",
                        "Bon état",
                        "État moyen",
                        "Mauvais état",
                        "À remplacer"
                    ]
                )

                fonctionnel = st.selectbox(
                    "Fonctionnel ?",
                    ["Oui", "Non"]
                )

            emplacement = st.text_input(
                "Emplacement"
            )

            photo = st.file_uploader(
                "Photo du matériel",
                type=["jpg", "jpeg", "png"]
            )

            observation = st.text_area(
                "Observation"
            )

            if st.button(
                "💾 Enregistrer le matériel",
                use_container_width=True,
                key="save_mat"
            ):

                errors = []

                if pos == "--- Sélectionner ---":
                    errors.append(
                        "Sélectionnez un POS."
                    )

                if type_mat == "--- Sélectionner ---":
                    errors.append(
                        "Sélectionnez le type de matériel."
                    )

                if marque_mat == "--- Sélectionner ---":
                    errors.append(
                        "Sélectionnez la marque du matériel."
                    )

                if errors:

                    for e in errors:
                        st.error(e)

                else:

                    append_dict_row(
                        SHEET_MATERIAL_POS,
                        {
                            "ID_Materiel": str(uuid.uuid4()),
                            "ID": str(uuid.uuid4()),
                            "Date_Installation": str(date_install),
                            "Date": str(date_install),
                            "ID_POS": pos,
                            "ID_Type_Materiel": clean_text(
                                type_row.get(
                                    "ID_Type_Materiel",
                                    ""
                                )
                                if type_row is not None
                                else ""
                            ),
                            "Type_Materiel": type_mat,
                            "Categorie_Materiel": categorie_mat,
                            "Catégorie_Materiel": categorie_mat,
                            "Marque_Materiel": marque_mat,
                            "Reference_Materiel": reference,
                            "Référence_Materiel": reference,
                            "Quantite": quantite,
                            "Quantité": quantite,
                            "Etat": etat,
                            "Fonctionnel": fonctionnel == "Oui",
                            "Emplacement": emplacement,
                            "Photo": photo.name if photo else "",
                            "Observation": observation,
                            "ID_User": st.session_state.user_id
                        }
                    )

                    st.success(
                        "✅ Matériel enregistré avec succès."
                    )

                    st.rerun()

    # -----------------------------------------------------
    # CONTROLE
    # -----------------------------------------------------
    with tab_control:

        if df_pos.empty or df_material_pos.empty:

            st.info(
                "Enregistrez d'abord un matériel pour un POS."
            )

        else:

            pos_c = st.selectbox(
                "POS à contrôler",
                ["--- Sélectionner ---"]
                + unique_sorted(df_pos, "ID_POS"),
                key="control_pos"
            )

            if pos_c != "--- Sélectionner ---":

                mats = df_material_pos[
                    df_material_pos["ID_POS"]
                    .astype(str)
                    .str.strip()
                    == pos_c
                ]

                if mats.empty:

                    st.info(
                        "Aucun matériel enregistré pour ce POS."
                    )

                else:

                    labels = []

                    for idx, row in mats.iterrows():

                        labels.append(
                            (
                                f'{clean_text(row.get("Type_Materiel", ""))} | '
                                f'{clean_text(row.get("Marque_Materiel", ""))} | '
                                f'{clean_text(row.get("ID_Materiel", row.get("ID", "")))}',
                                idx
                            )
                        )

                    label = st.selectbox(
                        "Matériel",
                        [x[0] for x in labels],
                        key="control_mat"
                    )

                    idx = next(
                        x[1]
                        for x in labels
                        if x[0] == label
                    )

                    row = mats.loc[idx]

                    brand = clean_text(
                        row.get(
                            "Marque_Materiel",
                            ""
                        )
                    )

                    conform = "Non"

                    if (
                        not df_distribution.empty
                        and "Marque" in df_distribution.columns
                    ):

                        d = df_distribution[
                            df_distribution["ID_POS"]
                            .astype(str)
                            .str.strip()
                            == pos_c
                        ]

                        brands = (
                            set(
                                d["Marque"]
                                .astype(str)
                                .str.strip()
                                .str.lower()
                            )
                            if not d.empty
                            else set()
                        )

                        if brand.lower() in brands:
                            conform = "Oui"

                    st.info(
                        f"Produit de la marque **{brand}** "
                        f"présent dans ce POS : **{conform}**"
                    )

                    c1, c2 = st.columns(2)

                    with c1:

                        dcontrol = st.date_input(
                            "Date du contrôle",
                            value=datetime.now().date(),
                            key="dc"
                        )

                        econtrol = st.selectbox(
                            "État constaté",
                            [
                                "Neuf",
                                "Bon état",
                                "État moyen",
                                "Mauvais état",
                                "À remplacer"
                            ],
                            key="ec"
                        )

                    with c2:

                        fcontrol = st.selectbox(
                            "Fonctionnel ?",
                            ["Oui", "Non"],
                            key="fc"
                        )

                        action = st.selectbox(
                            "Action nécessaire",
                            [
                                "Aucune",
                                "Maintenance",
                                "Réparation",
                                "Remplacement",
                                "Retrait",
                                "Nouvelle installation"
                            ],
                            key="ac"
                        )

                    photo_c = st.file_uploader(
                        "Photo du contrôle",
                        type=["jpg", "jpeg", "png"],
                        key="pc"
                    )

                    obs_c = st.text_area(
                        "Observation",
                        key="oc"
                    )

                    if st.button(
                        "💾 Enregistrer le contrôle",
                        use_container_width=True,
                        key="save_control"
                    ):

                        append_dict_row(
                            SHEET_MATERIAL_CONTROL,
                            {
                                "ID_Controle": str(uuid.uuid4()),
                                "ID": str(uuid.uuid4()),
                                "Date_Controle": str(dcontrol),
                                "Date": str(dcontrol),
                                "ID_POS": pos_c,
                                "ID_Materiel": clean_text(
                                    row.get(
                                        "ID_Materiel",
                                        row.get("ID", "")
                                    )
                                ),
                                "Etat": econtrol,
                                "Fonctionnel": fcontrol == "Oui",
                                "Conforme_Marque": conform == "Oui",
                                "Produit_Marque_Presente": conform == "Oui",
                                "Photo": photo_c.name if photo_c else "",
                                "Observation": obs_c,
                                "Action_Necessaire": action,
                                "ID_User": st.session_state.user_id
                            }
                        )

                        st.success(
                            "✅ Contrôle enregistré."
                        )

                        st.rerun()

    # -----------------------------------------------------
    # HISTORIQUE
    # -----------------------------------------------------
    with tab_history:

        st.subheader(
            "📋 Matériels installés"
        )

        if not df_material_pos.empty:

            st.dataframe(
                df_material_pos,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucun matériel enregistré."
            )

        st.subheader(
            "🔎 Contrôles effectués"
        )

        if not df_material_control.empty:

            st.dataframe(
                df_material_control,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucun contrôle enregistré."
            )


# =========================================================
# RELEVE PRIX
# =========================================================
elif menu == "💰 Relevé Prix":

    st.header("💰 Relevé Prix")

    if df_pos.empty or df_products.empty:

        st.warning(
            "Les tables POS et Produits doivent être renseignées."
        )

        st.stop()

    # -----------------------------------------------------
    # POS
    # -----------------------------------------------------
    pos = st.selectbox(
        "POS",
        ["--- Sélectionner ---"]
        + unique_sorted(df_pos, "ID_POS"),
        key="price_pos"
    )

    # -----------------------------------------------------
    # PRODUIT
    # -----------------------------------------------------
    st.subheader("📦 Produit")

    marque, categorie, famille, produit, capacite = product_selector(
        prefix="price"
    )

    # -----------------------------------------------------
    # PRIX
    # -----------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:

        prix = st.number_input(
            "Prix de vente",
            min_value=0.0,
            step=100.0,
            key="price_value"
        )

    with col2:

        promo = st.selectbox(
            "En promotion ?",
            ["Non", "Oui"],
            key="price_promo"
        )

    prix_promo = st.number_input(
        "Prix promotionnel",
        min_value=0.0,
        step=100.0,
        key="price_promo_value"
    )

    date_releve = st.date_input(
        "Date du relevé",
        value=datetime.now().date(),
        key="price_date"
    )

    remarque = st.text_area(
        "Remarque",
        key="price_remarque"
    )

    if st.button(
        "💾 Enregistrer le prix",
        use_container_width=True,
        key="price_save"
    ):

        errors = []

        if pos == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez un POS."
            )

        if marque == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une marque."
            )

        if categorie == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une catégorie."
            )

        if famille == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une famille."
            )

        if produit == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez un produit."
            )

        if capacite == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une capacité/dimension."
            )

        if prix <= 0:
            errors.append(
                "Le prix doit être supérieur à 0."
            )

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

            st.success(
                "✅ Relevé prix enregistré."
            )

            st.rerun()


# =========================================================
# ENQUETE
# =========================================================
elif menu == "📝 Enquête":

    st.header("📝 Enquête")

    if df_pos.empty or df_products.empty:

        st.warning(
            "Les tables POS et Produits doivent être renseignées."
        )

        st.stop()

    if df_subjects.empty:

        st.warning(
            "Aucun sujet d'enquête disponible. "
            "Ajoutez d'abord des lignes dans Enquetes_Sujets."
        )

        st.stop()

    # -----------------------------------------------------
    # SUJET
    # -----------------------------------------------------
    sujet = st.selectbox(
        "Sujet de l'enquête",
        ["--- Sélectionner ---"]
        + unique_sorted(
            df_subjects,
            "Nom_Enquete"
        ),
        key="survey_subject"
    )

    # -----------------------------------------------------
    # POS
    # -----------------------------------------------------
    pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"]
        + unique_sorted(
            df_pos,
            "ID_POS"
        ),
        key="survey_pos"
    )

    st.subheader(
        "Produit observé"
    )

    # -----------------------------------------------------
    # MARQUES EXPOSEES
    # -----------------------------------------------------
    marques_exposees = st.multiselect(
        "Marques exposées",
        unique_sorted(
            df_products,
            "Marque"
        ),
        key="survey_brands_exposed"
    )

    # -----------------------------------------------------
    # PRODUIT EN CASCADE
    # -----------------------------------------------------
    marque, categorie, famille, produit, capacite = product_selector(
        prefix="survey"
    )

    # -----------------------------------------------------
    # AUTRES INFORMATIONS
    # -----------------------------------------------------
    col1, col2 = st.columns(2)

    with col1:

        prix = st.number_input(
            "Prix",
            min_value=0.0,
            step=100.0,
            key="survey_price"
        )

        stock = st.selectbox(
            "Stock disponible ?",
            ["Oui", "Non"],
            key="survey_stock"
        )

    with col2:

        promo = st.selectbox(
            "En promotion ?",
            ["Oui", "Non"],
            key="survey_promo"
        )

        frequence = st.number_input(
            "Fréquence de vente / jour",
            min_value=0.0,
            step=1.0,
            key="survey_frequency"
        )

    remarque = st.text_area(
        "Remarque",
        key="survey_remark"
    )

    if st.button(
        "💾 Enregistrer l'enquête",
        use_container_width=True,
        key="survey_save"
    ):

        errors = []

        if sujet == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez le sujet de l'enquête."
            )

        if pos == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez le POS."
            )

        if not marques_exposees:
            errors.append(
                "Sélectionnez au moins une marque exposée."
            )

        if marque == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une marque."
            )

        if categorie == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une catégorie."
            )

        if famille == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une famille."
            )

        if produit == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez un produit."
            )

        if capacite == "--- Sélectionner ---":
            errors.append(
                "Sélectionnez une capacité/dimension."
            )

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
                    ", ".join(marques_exposees),
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

            st.success(
                "✅ Enquête enregistrée."
            )

            st.rerun()


# =========================================================
# VISITES POS
# =========================================================
elif menu == "🚗 Visites POS":

    st.header("🚗 Visites POS")

    if df_pos.empty:
        st.warning("La table POS est vide.")
        st.stop()

    st.info(
        "Le module Visites POS est disponible. "
        "La table utilisée est : Visites_POS."
    )

    pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"]
        + unique_sorted(df_pos, "ID_POS"),
        key="visit_pos"
    )

    date_visite = st.date_input(
        "Date de visite",
        value=datetime.now().date(),
        key="visit_date"
    )

    motif = st.text_input(
        "Motif de la visite",
        key="visit_reason"
    )

    observation = st.text_area(
        "Observation",
        key="visit_observation"
    )

    if st.button(
        "💾 Enregistrer la visite",
        use_container_width=True,
        key="visit_save"
    ):

        if pos == "--- Sélectionner ---":

            st.error(
                "Sélectionnez un POS."
            )

        else:

            append_dict_row(
                SHEET_VISITS,
                {
                    "ID_Visite": str(uuid.uuid4()),
                    "ID": str(uuid.uuid4()),
                    "Date_Visite": str(date_visite),
                    "Date": str(date_visite),
                    "ID_POS": pos,
                    "Motif": motif,
                    "Observation": observation,
                    "ID_User": st.session_state.user_id
                }
            )

            st.success(
                "✅ Visite enregistrée."
            )

            st.rerun()

    st.markdown("---")
    st.subheader("📋 Historique des visites")

    if not df_visits.empty:

        st.dataframe(
            df_visits.tail(50),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucune visite enregistrée."
        )


# =========================================================
# OBJECTIFS POS
# =========================================================
elif menu == "🎯 Objectifs POS":

    st.header("🎯 Objectifs POS")

    if df_pos.empty:
        st.warning("La table POS est vide.")
        st.stop()

    st.info(
        "Gestion des objectifs par POS."
    )

    pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"]
        + unique_sorted(df_pos, "ID_POS"),
        key="objective_pos"
    )

    periode = st.text_input(
        "Période",
        placeholder="Exemple : Août 2026",
        key="objective_period"
    )

    objectif_distribution = st.number_input(
        "Objectif distribution numérique",
        min_value=0,
        step=1,
        key="objective_distribution"
    )

    objectif_prix = st.number_input(
        "Nombre de relevés prix attendu",
        min_value=0,
        step=1,
        key="objective_price"
    )

    objectif_enquete = st.number_input(
        "Nombre d'enquêtes attendu",
        min_value=0,
        step=1,
        key="objective_survey"
    )

    observation = st.text_area(
        "Observation",
        key="objective_observation"
    )

    if st.button(
        "💾 Enregistrer l'objectif",
        use_container_width=True,
        key="objective_save"
    ):

        if pos == "--- Sélectionner ---":

            st.error(
                "Sélectionnez un POS."
            )

        elif not periode.strip():

            st.error(
                "Saisissez la période."
            )

        else:

            append_dict_row(
                SHEET_OBJECTIVES,
                {
                    "ID_Objectif": str(uuid.uuid4()),
                    "ID": str(uuid.uuid4()),
                    "Date": str(datetime.now().date()),
                    "Periode": periode,
                    "Période": periode,
                    "ID_POS": pos,
                    "Objectif_Distribution": objectif_distribution,
                    "Objectif_Prix": objectif_prix,
                    "Objectif_Enquete": objectif_enquete,
                    "Observation": observation,
                    "ID_User": st.session_state.user_id
                }
            )

            st.success(
                "✅ Objectif enregistré."
            )

            st.rerun()

    st.markdown("---")
    st.subheader("📋 Objectifs enregistrés")

    if not df_objectives.empty:

        st.dataframe(
            df_objectives,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucun objectif enregistré."
        )


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
    total_material = len(df_material_pos)

    total_brands = (
        df_products["Marque"].nunique()
        if (
            not df_products.empty
            and "Marque" in df_products.columns
        )
        else 0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("POS", total_pos)
    c2.metric(
        "Relevés distribution",
        total_distribution
    )
    c3.metric(
        "Relevés prix",
        total_price
    )
    c4.metric(
        "Enquêtes",
        total_surveys
    )
    c5.metric(
        "Marques",
        total_brands
    )
    c6.metric(
        "Matériels",
        total_material
    )

    st.markdown("---")

    # -----------------------------------------------------
    # DISTRIBUTION PAR MARQUE
    # -----------------------------------------------------
    if not df_distribution.empty:

        st.subheader(
            "📦 Distribution par marque"
        )

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
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(chart)

        st.subheader(
            "🏷️ Distribution par catégorie"
        )

        if (
            "Catégorie" in df_distribution.columns
            and "Quantite" in dist.columns
        ):

            chart_cat = (
                dist.groupby(
                    "Catégorie"
                )["Quantite"]
                .sum()
                .sort_values(
                    ascending=False
                )
            )

            st.bar_chart(chart_cat)

    # -----------------------------------------------------
    # PRIX
    # -----------------------------------------------------
    if not df_prices.empty:

        st.subheader(
            "💰 Analyse des prix"
        )

        price_df = df_prices.copy()

        # Selon les colonnes de la feuille
        price_column = None

        if "Prix_Vente" in price_df.columns:
            price_column = "Prix_Vente"
        elif "Prix" in price_df.columns:
            price_column = "Prix"

        if price_column:

            price_df[price_column] = pd.to_numeric(
                price_df[price_column],
                errors="coerce"
            )

            if "Marque" in price_df.columns:

                avg_price = (
                    price_df.groupby(
                        "Marque"
                    )[price_column]
                    .mean()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(avg_price)

                price_summary = (
                    price_df.groupby("Marque")
                    .agg(
                        Prix_Moyen=(
                            price_column,
                            "mean"
                        ),
                        Prix_Min=(
                            price_column,
                            "min"
                        ),
                        Prix_Max=(
                            price_column,
                            "max"
                        ),
                        Nb_Releves=(
                            price_column,
                            "count"
                        )
                    )
                    .reset_index()
                    .sort_values(
                        "Prix_Moyen",
                        ascending=False
                    )
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

        st.subheader(
            "📝 Résultats des enquêtes"
        )

        if "Marque" in df_surveys.columns:

            survey_brand = (
                df_surveys["Marque"]
                .astype(str)
                .value_counts()
            )

            st.bar_chart(
                survey_brand
            )

        frequency_column = None

        if "Frequence_Vente_Jour" in df_surveys.columns:
            frequency_column = "Frequence_Vente_Jour"
        elif "Frequence" in df_surveys.columns:
            frequency_column = "Frequence"

        if frequency_column:

            freq_df = df_surveys.copy()

            freq_df[frequency_column] = pd.to_numeric(
                freq_df[frequency_column],
                errors="coerce"
            )

            if "Marque" in freq_df.columns:

                avg_freq = (
                    freq_df.groupby(
                        "Marque"
                    )[frequency_column]
                    .mean()
                    .sort_values(
                        ascending=False
                    )
                )

                st.subheader(
                    "📊 Fréquence moyenne de vente / jour"
                )

                st.bar_chart(
                    avg_freq
                )

    # -----------------------------------------------------
    # TABLES
    # -----------------------------------------------------
    st.markdown("---")

    st.subheader(
        "📋 Données disponibles"
    )

    tabs = st.tabs(
        [
            "Distribution",
            "Prix",
            "Enquêtes",
            "Profils",
            "Matériels",
            "Contrôles",
            "Visites",
            "Objectifs"
        ]
    )

    with tabs[0]:

        if not df_distribution.empty:

            st.dataframe(
                df_distribution,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[1]:

        if not df_prices.empty:

            st.dataframe(
                df_prices,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[2]:

        if not df_surveys.empty:

            st.dataframe(
                df_surveys,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[3]:

        if not df_profile.empty:

            st.dataframe(
                df_profile,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[4]:

        if not df_material_pos.empty:

            st.dataframe(
                df_material_pos,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[5]:

        if not df_material_control.empty:

            st.dataframe(
                df_material_control,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[6]:

        if not df_visits.empty:

            st.dataframe(
                df_visits,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )

    with tabs[7]:

        if not df_objectives.empty:

            st.dataframe(
                df_objectives,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucune donnée."
            )
