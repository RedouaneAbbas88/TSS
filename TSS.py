import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
import io
import uuid
import time
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
DRIVE_MATERIAL_FOLDER = "Data_Info_Materiel"


# =========================================================
# CONNEXION GOOGLE
# =========================================================

@st.cache_resource
def get_client():

    creds = Credentials.from_service_account_info(
        st.secrets["google"],
        scopes=SCOPES
    )

    return gspread.authorize(creds)


client = get_client()


@st.cache_resource
def get_spreadsheet():

    return client.open_by_key(SPREADSHEET_ID)


@st.cache_resource(show_spinner=False)
def _get_worksheet_cached(sheet_name):
    """Réutilise l'objet worksheet pour éviter de redemander ses métadonnées à chaque rerun."""
    return get_spreadsheet().worksheet(sheet_name)


def get_ws(sheet_name):

    try:

        return _get_worksheet_cached(sheet_name)

    except gspread.WorksheetNotFound:

        st.error(
            f"❌ La feuille Google Sheets '{sheet_name}' "
            f"n'existe pas."
        )

        st.stop()

    except gspread.exceptions.APIError as e:

        error_text = str(e)

        if "429" in error_text:

            st.error(
                "❌ Google Sheets a atteint la limite de lectures.\n\n"
                "Erreur : 429 - Quota exceeded.\n\n"
                "Attendez quelques minutes puis rechargez "
                "l'application."
            )

        elif "403" in error_text:

            st.error(
                "❌ Accès refusé au Google Sheet.\n\n"
                "Vérifiez que le compte de service utilisé "
                "dans st.secrets['google'] a accès au fichier."
            )

        elif "404" in error_text:

            st.error(
                "❌ Google Sheet introuvable.\n\n"
                "Vérifiez le SPREADSHEET_ID."
            )

        else:

            st.error(
                f"❌ Erreur Google Sheets : {error_text}"
            )

        st.stop()


# =========================================================
# GOOGLE DRIVE - PHOTOS DU MATERIEL
# =========================================================

@st.cache_resource
def get_drive_service():
    creds = Credentials.from_service_account_info(
        st.secrets["google"],
        scopes=SCOPES
    )
    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False
    )


def get_or_create_drive_folder():
    """Retourne l'ID du dossier Google Drive utilisé pour les photos."""
    service = get_drive_service()

    response = service.files().list(
        q=(
            f"name = '{DRIVE_MATERIAL_FOLDER}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        ),
        spaces="drive",
        fields="files(id,name)",
        pageSize=1
    ).execute()

    files = response.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": DRIVE_MATERIAL_FOLDER,
        "mimeType": "application/vnd.google-apps.folder"
    }

    folder = service.files().create(
        body=metadata,
        fields="id"
    ).execute()

    return folder["id"]


def upload_photo_to_drive(uploaded_file, prefix="materiel"):
    """Upload une photo dans Google Drive et retourne son lien."""
    if uploaded_file is None:
        return ""

    try:
        service = get_drive_service()
        folder_id = get_or_create_drive_folder()

        extension = "jpg"
        original_name = clean_text(uploaded_file.name)
        if "." in original_name:
            extension = original_name.rsplit(".", 1)[-1].lower()
            if extension not in ["jpg", "jpeg", "png"]:
                extension = "jpg"

        filename = (
            f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:8]}.{extension}"
        )

        file_bytes = uploaded_file.getvalue()
        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=uploaded_file.type or "image/jpeg",
            resumable=False
        )

        metadata = {
            "name": filename,
            "parents": [folder_id]
        }

        created = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink"
        ).execute()

        file_id = created["id"]

        # Rend le fichier accessible par lien.
        # Si la politique Google Workspace interdit le partage public,
        # on conserve quand même le lien Drive normal.
        try:
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id"
            ).execute()
        except HttpError:
            pass

        return created.get(
            "webViewLink",
            f"https://drive.google.com/file/d/{file_id}/view"
        )

    except Exception as e:
        st.error(
            "❌ Impossible d'envoyer la photo vers Google Drive : "
            f"{e}"
        )
        return ""


# =========================================================
# CHARGEMENT DES DONNEES
# =========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def load_sheet_headers(sheet_name):
    """Cache les en-têtes : évite un appel row_values(1) à chaque enregistrement."""
    ws = get_ws(sheet_name)
    return [str(value).strip() for value in ws.row_values(1)]


@st.cache_data(
    ttl=600,
    show_spinner=False
)
def load_sheet(sheet_name):

    try:

        ws = get_ws(sheet_name)

        data = ws.get_all_records()

        df = pd.DataFrame(data)

        if not df.empty:

            df.columns = (
                df.columns
                .astype(str)
                .str.strip()
            )

        return df

    except gspread.exceptions.APIError as e:

        error_text = str(e)

        if "429" in error_text:

            st.error(
                "❌ Quota Google Sheets dépassé.\n\n"
                "La limite de lectures par minute a été atteinte.\n\n"
                "Attendez quelques minutes avant de relancer."
            )

        else:

            st.error(
                f"❌ Erreur Google Sheets : {error_text}"
            )

        return pd.DataFrame()

    except Exception as e:

        st.error(
            f"❌ Impossible de charger la feuille "
            f"'{sheet_name}'.\n\n"
            f"Détail : {e}"
        )

        return pd.DataFrame()


def clear_sheet_cache(sheet_name=None):

    try:

        if sheet_name:
            load_sheet.clear(sheet_name)
            load_sheet_headers.clear(sheet_name)
        else:
            load_sheet.clear()
            load_sheet_headers.clear()

    except Exception:

        try:
            load_sheet.clear()
        except Exception:
            pass


# =========================================================
# ECRITURE GOOGLE SHEETS
# =========================================================

def append_row(sheet_name, row):

    max_attempts = 3

    for attempt in range(max_attempts):

        try:

            ws = get_ws(sheet_name)

            ws.append_row(
                row,
                value_input_option="USER_ENTERED"
            )

            clear_sheet_cache(sheet_name)

            return True

        except gspread.exceptions.APIError as e:

            error_text = str(e)

            if "429" in error_text:

                if attempt < max_attempts - 1:

                    time.sleep(
                        5 * (2 ** attempt)
                    )

                    continue

                st.error(
                    "❌ Google Sheets refuse actuellement "
                    "l'écriture à cause de la limite de quota "
                    "429.\n\n"
                    "Attendez quelques minutes puis réessayez."
                )

                return False

            st.error(
                f"❌ Erreur Google Sheets : {error_text}"
            )

            return False

        except Exception as e:

            st.error(
                f"❌ Erreur lors de l'enregistrement : {e}"
            )

            return False

    return False


def append_dict_row(sheet_name, values):

    try:

        ws = get_ws(sheet_name)

        headers = load_sheet_headers(sheet_name)

        row = [
            values.get(header, "")
            for header in headers
        ]

        return append_row(
            sheet_name,
            row
        )

    except Exception as e:

        st.error(
            f"❌ Impossible de préparer "
            f"l'enregistrement : {e}"
        )

        return False


# =========================================================
# OUTILS
# =========================================================

def clean_text(value):

    if pd.isna(value):
        return ""

    return str(value).strip()


def unique_sorted(df, column):

    if df is None:
        return []

    if df.empty:
        return []

    if column not in df.columns:
        return []

    values = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
    )

    values = [
        x
        for x in values.unique().tolist()
        if x
    ]

    return sorted(values)


def filter_products(
    products,
    marque="",
    categorie="",
    famille="",
    produit=""
):

    if products is None:
        return pd.DataFrame()

    if products.empty:
        return products

    result = products.copy()

    if marque and "Marque" in result.columns:

        result = result[
            result["Marque"]
            .astype(str)
            .str.strip()
            == marque.strip()
        ]

    if categorie and "Catégorie" in result.columns:

        result = result[
            result["Catégorie"]
            .astype(str)
            .str.strip()
            == categorie.strip()
        ]

    if famille and "Famille" in result.columns:

        result = result[
            result["Famille"]
            .astype(str)
            .str.strip()
            == famille.strip()
        ]

    if produit and "Produit" in result.columns:

        result = result[
            result["Produit"]
            .astype(str)
            .str.strip()
            == produit.strip()
        ]

    return result


# =========================================================
# CASCADE PRODUITS + AJOUT D'UN NOUVEAU PRODUIT
# =========================================================

PLACEHOLDER = "--- Sélectionner ---"


def product_cascade(
    df_products,
    prefix="product",
    allow_add=False
):
    """Sélection en cascade avec possibilité d'ajouter un produit.

    La feuille Produits doit contenir exactement les colonnes du référentiel :
    ID_Produit, Marque, Catégorie, Famille, Produit,
    Capacité_Dimension, Reference, Statut.
    """

    if df_products is None:
        df_products = pd.DataFrame()

    # Après l'ajout, appliquer les valeurs au prochain affichage,
    # une fois les nouvelles données rechargées depuis Google Sheets.
    pending_key = f"{prefix}_pending_product"
    pending = st.session_state.pop(pending_key, None)
    if pending:
        for field, value in pending.items():
            st.session_state[f"{prefix}_{field}"] = value

    # Normaliser les colonnes disponibles sans modifier la feuille.
    required_columns = [
        "ID_Produit",
        "Marque",
        "Catégorie",
        "Famille",
        "Produit",
        "Capacité_Dimension",
        "Reference",
        "Statut"
    ]

    for column in required_columns:
        if column not in df_products.columns:
            df_products[column] = ""

    # MARQUE
    marque_values = unique_sorted(df_products, "Marque")
    marque = st.selectbox(
        "Marque",
        [PLACEHOLDER] + marque_values,
        key=f"{prefix}_marque"
    )

    # CATEGORIE
    temp = filter_products(
        df_products,
        marque="" if marque == PLACEHOLDER else marque
    )
    categorie_values = unique_sorted(temp, "Catégorie")
    categorie = st.selectbox(
        "Catégorie",
        [PLACEHOLDER] + categorie_values,
        key=f"{prefix}_categorie"
    )

    # FAMILLE
    temp = filter_products(
        df_products,
        marque="" if marque == PLACEHOLDER else marque,
        categorie="" if categorie == PLACEHOLDER else categorie
    )
    famille_values = unique_sorted(temp, "Famille")
    famille = st.selectbox(
        "Famille",
        [PLACEHOLDER] + famille_values,
        key=f"{prefix}_famille"
    )

    # PRODUIT : bouton + placé à côté du titre, comme pour l'ajout d'un POS.
    temp = filter_products(
        df_products,
        marque="" if marque == PLACEHOLDER else marque,
        categorie="" if categorie == PLACEHOLDER else categorie,
        famille="" if famille == PLACEHOLDER else famille
    )
    product_values = unique_sorted(temp, "Produit")

    product_label_col, product_add_col = st.columns([5, 1])
    with product_label_col:
        st.markdown("**Produit**")
    with product_add_col:
        if allow_add:
            add_product_popover = st.popover("＋", help="Ajouter un nouveau produit")
        else:
            add_product_popover = None

    produit = st.selectbox(
        "Produit",
        [PLACEHOLDER] + product_values,
        key=f"{prefix}_produit",
        label_visibility="collapsed"
    )

    # CAPACITE / DIMENSION
    temp = filter_products(
        df_products,
        marque="" if marque == PLACEHOLDER else marque,
        categorie="" if categorie == PLACEHOLDER else categorie,
        famille="" if famille == PLACEHOLDER else famille,
        produit="" if produit == PLACEHOLDER else produit
    )
    dimension_values = unique_sorted(temp, "Capacité_Dimension")
    capacite = st.selectbox(
        "Capacité / Dimension",
        [PLACEHOLDER] + dimension_values,
        key=f"{prefix}_capacite"
    )

    # Le formulaire d'ajout n'apparaît que lorsque l'utilisateur clique sur +.
    if allow_add and add_product_popover is not None:
        with add_product_popover:
            st.markdown("**Ajouter un nouveau produit**")
            st.caption(
                "Le champ Produit correspond au code produit réel (ex. CCE4T618ES). "
                "L'ID_Produit est généré automatiquement."
            )

            with st.form(f"{prefix}_add_product_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    new_marque = st.text_input(
                        "Marque *",
                        value="" if marque == PLACEHOLDER else marque,
                        key=f"{prefix}_new_marque"
                    )
                    new_categorie = st.text_input(
                        "Catégorie *",
                        value="" if categorie == PLACEHOLDER else categorie,
                        key=f"{prefix}_new_categorie"
                    )
                    new_famille = st.text_input(
                        "Famille *",
                        value="" if famille == PLACEHOLDER else famille,
                        key=f"{prefix}_new_famille"
                    )
                with c2:
                    new_produit = st.text_input(
                        "Produit / Code produit *",
                        value="" if produit == PLACEHOLDER else produit,
                        key=f"{prefix}_new_produit",
                        help="Saisir le code produit exact, par exemple CCE4T618ES."
                    )
                    new_dimension = st.text_input(
                        "Capacité / Dimension *",
                        value="" if capacite == PLACEHOLDER else capacite,
                        key=f"{prefix}_new_dimension"
                    )
                    new_reference = st.text_input(
                        "Référence / Unité (L, kg, pouces...) *",
                        key=f"{prefix}_new_reference"
                    )

                submitted = st.form_submit_button(
                    "💾 Enregistrer le produit",
                    use_container_width=True
                )

            if submitted:
                product_data = {
                    "Marque": clean_text(new_marque),
                    "Catégorie": clean_text(new_categorie),
                    "Famille": clean_text(new_famille),
                    "Produit": clean_text(new_produit),
                    "Capacité_Dimension": clean_text(new_dimension),
                    "Reference": clean_text(new_reference),
                    "Statut": "Actif"
                }

                missing = [name for name, value in product_data.items() if not value]
                if missing:
                    st.error(
                        "Veuillez renseigner tous les champs obligatoires : "
                        + ", ".join(missing)
                    )
                else:
                    try:
                        products_ws = get_ws(SHEET_PRODUCTS)
                        headers = [str(x).strip() for x in products_ws.row_values(1)]
                        missing_headers = [h for h in required_columns if h not in headers]

                        if missing_headers:
                            st.error(
                                "La feuille Produits doit contenir ces colonnes "
                                "dans sa première ligne : " + ", ".join(missing_headers)
                            )
                        else:
                            existing_codes = (
                                df_products.get("Produit", pd.Series(dtype=str))
                                .fillna("").astype(str).str.strip().str.casefold()
                            )
                            if (existing_codes == product_data["Produit"].casefold()).any():
                                st.warning("Ce produit existe déjà dans le référentiel Produits.")
                            else:
                                existing_ids = []
                                if not df_products.empty and "ID_Produit" in df_products.columns:
                                    existing_ids = (
                                        df_products["ID_Produit"].dropna().astype(str).str.strip().tolist()
                                    )
                                numeric_ids = [
                                    int(existing_id[1:])
                                    for existing_id in existing_ids
                                    if existing_id.upper().startswith("P")
                                    and existing_id[1:].isdigit()
                                ]
                                product_data["ID_Produit"] = f"P{max(numeric_ids, default=0) + 1:03d}"

                                success = append_dict_row(SHEET_PRODUCTS, product_data)
                                if success:
                                    st.session_state[pending_key] = {
                                        "marque": product_data["Marque"],
                                        "categorie": product_data["Catégorie"],
                                        "famille": product_data["Famille"],
                                        "produit": product_data["Produit"],
                                        "capacite": product_data["Capacité_Dimension"]
                                    }
                                    clear_sheet_cache(SHEET_PRODUCTS)
                                    st.success("✅ Nouveau produit ajouté au référentiel.")
                                    st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de l'ajout du produit : {e}")

    return marque, categorie, famille, produit, capacite


# =========================================================
# SESSION
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


def normalize_visit_type(value):
    """Normalise les quatre activités planifiables dans Visites_POS."""
    value = clean_text(value).strip().upper()
    value = value.replace("É", "E").replace("È", "E").replace("Ê", "E")
    value = value.replace("_", " ").replace("-", " ")
    value = " ".join(value.split())
    if value in ("DN", "DISTRIBUTION NUMERIQUE"):
        return "DN"
    if value in ("PRIX", "RELEVE PRIX", "RELEVE DES PRIX"):
        return "PRIX"
    if value in ("VISITES POS", "VISITE POS", "VISITE", "VISITES"):
        return "VISITES_POS"
    if value in ("MATERIEL POS", "MATERIEL", "MATERIELS POS", "CONTROLE MATERIEL"):
        return "MATERIEL_POS"
    return ""  # Anciennes affectations sans Type_Visite : compatibilité historique.


def visit_type_label(value):
    labels = {
        "DN": "Distribution numérique",
        "PRIX": "Relevé des prix",
        "VISITES_POS": "Visites POS",
        "MATERIEL_POS": "Matériel POS"
    }
    return labels.get(normalize_visit_type(value), "Activité non précisée")


def normalize_role(value):
    """Normalise les rôles pour appliquer les droits d'accès."""
    role = clean_text(value).strip().lower()
    role = " ".join(role.replace("_", " ").replace("-", " ").split())
    return role


def get_user_planned_pos(df_visits, visit_date, user_id, visit_type):
    """Retourne les POS planifiés pour un utilisateur, une date et une activité."""
    if df_visits is None or df_visits.empty:
        return []
    required = {"ID_POS", "ID_User"}
    if not required.issubset(set(df_visits.columns)):
        return []
    date_column = next((c for c in ("Date_Visite", "Date") if c in df_visits.columns), None)
    if date_column is None:
        return []
    visits = df_visits.copy()
    visits["ID_User"] = visits["ID_User"].apply(clean_text)
    visits["ID_POS"] = visits["ID_POS"].apply(clean_text)
    visits["_date_filter"] = pd.to_datetime(visits[date_column], errors="coerce", dayfirst=True).dt.date
    target_type = normalize_visit_type(visit_type)
    if "Type_Visite" in visits.columns:
        visits["_type_filter"] = visits["Type_Visite"].apply(normalize_visit_type)
        # Les anciennes lignes sans type restent visibles dans les deux modules.
        type_mask = visits["_type_filter"].isin([target_type, ""])
    else:
        type_mask = pd.Series(True, index=visits.index)
    filtered = visits[
        (visits["ID_User"] == clean_text(user_id))
        & (visits["_date_filter"] == visit_date)
        & (visits["ID_POS"] != "")
        & type_mask
    ]
    return sorted(filtered["ID_POS"].drop_duplicates().tolist())


def build_planned_pos_table(df_pos, planned_pos_ids, df_visits=None, user_id=None, visit_date=None, visit_type="DN"):
    """Construit le planning personnel d'une activité avec son statut propre."""
    empty_cols = ["ID_POS", "Nom_POS", "Type visite", "Statut", "Début", "Fin"]
    if df_pos is None or df_pos.empty or not planned_pos_ids:
        return pd.DataFrame(columns=empty_cols)
    pos = df_pos.copy()
    if "ID_POS" not in pos.columns:
        planned = pd.DataFrame({"ID_POS": planned_pos_ids})
    else:
        pos["ID_POS"] = pos["ID_POS"].apply(clean_text)
        planned = pos[pos["ID_POS"].isin(planned_pos_ids)].drop_duplicates(subset=["ID_POS"]).copy()
    if "Nom_POS" not in planned.columns:
        planned["Nom_POS"] = planned["Nom"] if "Nom" in planned.columns else ""
    planned["Type visite"] = visit_type_label(visit_type)
    planned["Statut"] = "Planifiée"
    planned["Début"] = ""
    planned["Fin"] = ""
    if df_visits is not None and not df_visits.empty:
        date_col = next((c for c in ("Date_Visite", "Date") if c in df_visits.columns), None)
        if date_col and {"ID_POS", "ID_User"}.issubset(df_visits.columns):
            v = df_visits.copy()
            v["ID_POS"] = v["ID_POS"].apply(clean_text)
            v["ID_User"] = v["ID_User"].apply(clean_text)
            v["_visit_date"] = pd.to_datetime(v[date_col], errors="coerce", dayfirst=True).dt.date
            if "Type_Visite" in v.columns:
                v["_type"] = v["Type_Visite"].apply(normalize_visit_type)
                v = v[v["_type"].isin([normalize_visit_type(visit_type), ""])]
            v = v[(v["ID_POS"].isin(planned_pos_ids)) & (v["ID_User"] == clean_text(user_id))]
            if visit_date is not None:
                v = v[v["_visit_date"] == visit_date]
            for _, row in v.drop_duplicates(subset=["ID_POS"], keep="last").iterrows():
                mask = planned["ID_POS"] == clean_text(row.get("ID_POS", ""))
                planned.loc[mask, "Statut"] = clean_text(row.get("Statut_Tournee", "")) or "Planifiée"
                planned.loc[mask, "Début"] = clean_text(row.get("Heure_Debut", ""))
                planned.loc[mask, "Fin"] = clean_text(row.get("Heure_Fin", ""))
    return planned[empty_cols].reset_index(drop=True)


def _column_letter(column_number):
    """Convertit un numéro de colonne (1-based) en lettre Google Sheets."""
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def ensure_sheet_columns(sheet_name, required_columns):
    """Ajoute à droite les colonnes manquantes sans modifier les données existantes."""
    headers = load_sheet_headers(sheet_name)
    missing = [column for column in required_columns if column not in headers]
    if not missing:
        return headers
    start_col = len(headers) + 1
    ws = get_ws(sheet_name)
    ws.update(
        f"{_column_letter(start_col)}1:{_column_letter(start_col + len(missing) - 1)}1",
        [missing],
        value_input_option="USER_ENTERED"
    )
    load_sheet_headers.clear(sheet_name)
    clear_sheet_cache(sheet_name)
    return headers + missing


def get_planned_visit_row(df_visits, pos_id, visit_date, user_id, visit_type):
    """Retourne la ligne Sheets correspondant au POS, utilisateur, date et activité."""
    if df_visits is None or df_visits.empty:
        return None, None
    date_col = next((c for c in ("Date_Visite", "Date") if c in df_visits.columns), None)
    if date_col is None or not {"ID_POS", "ID_User"}.issubset(df_visits.columns):
        return None, None
    v = df_visits.copy()
    v["_pos"] = v["ID_POS"].apply(clean_text)
    v["_user"] = v["ID_User"].apply(clean_text)
    v["_date"] = pd.to_datetime(v[date_col], errors="coerce", dayfirst=True).dt.date
    if "Type_Visite" in v.columns:
        v["_type"] = v["Type_Visite"].apply(normalize_visit_type)
        v = v[v["_type"].isin([normalize_visit_type(visit_type), ""])]
    matches = v[(v["_pos"] == clean_text(pos_id)) &
                (v["_user"] == clean_text(user_id)) &
                (v["_date"] == visit_date)]
    if matches.empty:
        return None, None
    # Si plusieurs lignes existent, privilégier la ligne du type exact.
    if "Type_Visite" in matches.columns:
        exact = matches[matches["_type"] == normalize_visit_type(visit_type)]
        if not exact.empty:
            matches = exact
    idx = matches.index[-1]
    return int(idx) + 2, matches.iloc[-1]


def update_visit_tournee(df_visits, pos_id, visit_date, user_id, visit_type, values):
    """Met à jour le suivi de tournée sur la ligne de l'activité concernée."""
    row_number, visit_row = get_planned_visit_row(df_visits, pos_id, visit_date, user_id, visit_type)
    if row_number is None:
        st.error("Affectation introuvable pour cette activité dans Visites_POS. Actualisez le planning ou contactez l'administrateur.")
        return False
    try:
        required_columns = ["Statut_Tournee", "Heure_Debut", "Heure_Fin", "Motif_Cloture", "Observation_Cloture"]
        headers = load_sheet_headers(SHEET_VISITS)
        missing = [column for column in required_columns if column not in headers]
        if missing:
            start_col = len(headers) + 1
            ws = get_ws(SHEET_VISITS)
            ws.update(
                f"{_column_letter(start_col)}1:{_column_letter(start_col + len(missing) - 1)}1",
                [missing], value_input_option="USER_ENTERED"
            )
            headers = headers + missing
            load_sheet_headers.clear(SHEET_VISITS)
        ws = get_ws(SHEET_VISITS)
        updates = []
        for column_name, value in values.items():
            if column_name in headers:
                col_number = headers.index(column_name) + 1
                updates.append({"range": f"{_column_letter(col_number)}{row_number}", "values": [[value]]})
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
        clear_sheet_cache(SHEET_VISITS)
        return True
    except Exception as exc:
        st.error(f"Impossible de mettre à jour la tournée : {exc}")
        return False


def render_visit_tournee(df_visits, selected_pos, visit_date, user_id, key_prefix, visit_type):
    """Démarre/ferme la tournée d'un POS pour une activité donnée."""
    if not selected_pos or selected_pos == "--- Sélectionner ---":
        st.info("Sélectionnez un POS dans votre planning pour démarrer cette activité.")
        return False
    row_number, visit_row = get_planned_visit_row(df_visits, selected_pos, visit_date, user_id, visit_type)
    if row_number is None:
        st.error("Ce POS ne correspond pas à une affectation de votre planning pour cette activité et cette date.")
        return False
    activity_label = visit_type_label(visit_type)
    status = clean_text(visit_row.get("Statut_Tournee", "")) or "Planifiée"
    st.markdown(f"#### 🚗 Tournée — {activity_label}")
    if status.lower() in ("planifiée", "planifiee", "planifie", ""):
        st.info("Cette activité est planifiée, mais la tournée n'a pas encore commencé.")
        if st.button("▶️ Démarrer la tournée", key=f"{key_prefix}_start_tournee", use_container_width=True):
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if update_visit_tournee(df_visits, selected_pos, visit_date, user_id, visit_type, {
                "Statut_Tournee": "En cours", "Heure_Debut": now_text,
                "Heure_Fin": "", "Motif_Cloture": "", "Observation_Cloture": ""
            }):
                st.success("Tournée démarrée. Vous pouvez maintenant effectuer plusieurs saisies pour cette activité.")
                st.rerun()
        return False
    if status.lower() in ("en cours", "en_cours", "encours"):
        started = clean_text(visit_row.get("Heure_Debut", ""))
        st.success(f"Tournée en cours{(' depuis ' + started) if started else ''}. Vous pouvez effectuer plusieurs saisies.")
        with st.form(f"{key_prefix}_close_tournee_form"):
            outcome = st.selectbox(
                "Résultat de l'activité",
                ["Visite effectuée", "POS fermé", "Responsable absent", "Refus d'accès", "Visite reportée", "Autre"],
                key=f"{key_prefix}_close_outcome"
            )
            close_observation = st.text_area("Observation de clôture (facultatif)", key=f"{key_prefix}_close_observation")
            close_clicked = st.form_submit_button("🔒 Clôturer la tournée", use_container_width=True)
        if close_clicked:
            final_status = "Visitée" if outcome == "Visite effectuée" else outcome
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if update_visit_tournee(df_visits, selected_pos, visit_date, user_id, visit_type, {
                "Statut_Tournee": final_status, "Heure_Fin": now_text,
                "Motif_Cloture": outcome, "Observation_Cloture": close_observation
            }):
                st.success(f"Activité clôturée : {final_status}.")
                st.rerun()
        return True
    st.warning(f"Cette activité est déjà clôturée : **{status}**.")
    return False


# =========================================================
# LOGIN
# =========================================================

if not st.session_state.logged_in:

    st.markdown(
        "<div class='main-title'>📊 Data_Info</div>",
        unsafe_allow_html=True
    )

    st.markdown(
        "<div class='small-title'>"
        "Market Data Collection & Analysis"
        "</div>",
        unsafe_allow_html=True
    )

    # Actualisation manuelle des données Google Sheets (notamment les noms utilisateurs).
    if st.button("🔄 Actualiser la liste des utilisateurs", use_container_width=True):
        load_sheet.clear()
        load_sheet_headers.clear()
        st.rerun()

    users = load_sheet(
        SHEET_USERS
    )

    if users.empty:

        st.error(
            "Impossible de charger la table Utilisateurs."
        )

        st.stop()

    if (
        "Nom" not in users.columns
        or "Password" not in users.columns
    ):

        st.error(
            "La table Utilisateurs doit contenir : "
            "ID_User, Nom, Email, Password, Role, Statut."
        )

        st.stop()

    users["Nom"] = (
        users["Nom"]
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
                active_users["Nom"]
                == selected_name
            ]

            if user.empty:

                st.error(
                    "Utilisateur introuvable."
                )

            else:

                user = user.iloc[0]

                if (
                    clean_text(
                        user["Password"]
                    )
                    != password.strip()
                ):

                    st.error(
                        "Mot de passe incorrect."
                    )

                else:

                    st.session_state.logged_in = True

                    st.session_state.user_name = (
                        clean_text(
                            user["Nom"]
                        )
                    )

                    st.session_state.role = (
                        clean_text(
                            user.get(
                                "Role",
                                "enqueteur"
                            )
                        ).lower()
                    )

                    st.session_state.user_id = (
                        clean_text(
                            user.get(
                                "ID_User",
                                ""
                            )
                        )
                    )

                    st.rerun()

    st.stop()


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.markdown(
    "## 📊 Data_Info"
)

st.sidebar.write(
    f"👤 **{st.session_state.user_name}**"
)

st.sidebar.write(
    f"🔑 Role : **{st.session_state.role}**"
)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Actualiser les données", use_container_width=True):
    # Vide le cache des feuilles et des en-têtes pour relire les valeurs actuelles
    # depuis Google Sheets sans attendre l'expiration automatique du cache.
    load_sheet.clear()
    load_sheet_headers.clear()
    st.rerun()

role_key = normalize_role(st.session_state.role)

all_menu_items = [
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

full_access_roles = {"admin", "administrateur", "administrator", "manager trade"}
supervisor_roles = {"superviseur trade", "supervisor trade"}
commercial_roles = {"commerciale", "commercial"}

if role_key in full_access_roles:
    menu_items = all_menu_items.copy()
    menu_items.insert(7, "⚙️ Paramétrage des visites")
elif role_key in supervisor_roles:
    # Accès à tous les modules opérationnels, sauf au paramétrage du planning.
    menu_items = all_menu_items.copy()
elif role_key in commercial_roles:
    # Le rôle Commerciale est limité au Profil Client.
    menu_items = ["👤 Profil Client"]
else:
    menu_items = []
    st.sidebar.error("Votre rôle n'est pas reconnu. Contactez l'administrateur.")

if not menu_items:
    st.error("Aucun accès n'est associé à votre rôle. Contactez l'administrateur.")
    st.stop()

menu = st.sidebar.radio(
    "Menu",
    menu_items
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

    st.header(
        "🏠 Tableau de bord"
    )

    # Seulement les tables utiles
    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    df_prices = load_sheet(
        SHEET_PRICES
    )

    df_surveys = load_sheet(
        SHEET_SURVEYS
    )

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

    st.subheader(
        "📌 Modules Data_Info"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.info(
            "**Distribution Numérique**\n\n"
            "Mesurer la présence des produits "
            "et des marques dans les POS."
        )

    with col2:

        st.info(
            "**Profil Client**\n\n"
            "Collecter les informations "
            "principales de chaque point de vente."
        )

    with col3:

        st.info(
            "**Relevé Prix**\n\n"
            "Collecter et comparer "
            "les prix du marché."
        )

    col4, col5 = st.columns(2)

    with col4:

        st.info(
            "**Enquête**\n\n"
            "Créer des enquêtes "
            "spécifiques sur le marché."
        )

    with col5:

        st.info(
            "**Statistiques**\n\n"
            "Suivre les KPI et l'évolution "
            "des données collectées."
        )


# =========================================================
# DISTRIBUTION NUMERIQUE
# =========================================================

elif menu == "📦 Distribution Numérique":

    st.header(
        "📦 Distribution Numérique"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    df_distribution = load_sheet(
        SHEET_DISTRIBUTION
    )

    if df_pos.empty:

        st.warning(
            "La table POS est vide."
        )

        st.stop()

    # Le référentiel Produits peut être vide au démarrage :
    # un produit pourra être créé directement depuis ce formulaire.

    # -----------------------------------------------------
    # DATE ET POS PLANIFIES POUR L'UTILISATEUR CONNECTE
    # -----------------------------------------------------

    date_visite = st.date_input(
        "Date de visite",
        value=datetime.now().date(),
        key="distribution_date"
    )

    # Le planning est mis en cache ; il est invalidé uniquement après une modification.
    df_visits_distribution = load_sheet(SHEET_VISITS)

    pos_names = get_user_planned_pos(
        df_visits_distribution,
        date_visite,
        st.session_state.user_id,
        "DN"
    )

    if not pos_names:
        st.warning(
            "Aucun POS n'est planifié pour votre utilisateur à cette date "
            "dans le tableau Visites POS."
        )
        st.stop()

    st.subheader("🗓️ Mon planning des visites")
    st.caption(
        f"{len(pos_names)} POS prévu(s) pour le {date_visite.strftime('%d/%m/%Y')}. "
        "Cette liste correspond uniquement à votre planning personnel."
    )
    st.dataframe(
        build_planned_pos_table(
            df_pos, pos_names, df_visits_distribution,
            st.session_state.user_id, date_visite, "DN"
        ),
        use_container_width=True,
        hide_index=True
    )

    if st.session_state.get("distribution_pos") not in ["--- Sélectionner ---"] + pos_names:
        st.session_state["distribution_pos"] = "--- Sélectionner ---"

    selected_pos = st.selectbox(
        "📍 Point de vente prévu pour cette visite",
        ["--- Sélectionner ---"] + pos_names,
        key="distribution_pos"
    )

    distribution_tournee_open = render_visit_tournee(
        df_visits_distribution, selected_pos, date_visite,
        st.session_state.user_id, "distribution", "DN"
    )
    if not distribution_tournee_open:
        st.info("Démarrez la tournée du POS sélectionné pour commencer la saisie. Une fois démarrée, vous pourrez enregistrer plusieurs produits avant de la clôturer.")
        st.stop()

    st.subheader(
        "📦 Produit"
    )

    (
        marque,
        categorie,
        famille,
        produit,
        capacite
    ) = product_cascade(
        df_products,
        prefix="distribution",
        allow_add=True
    )

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

        st.caption(f"Date de visite : {date_visite.strftime('%d/%m/%Y')}")

    remarque = st.text_area(
        "Remarque",
        key="distribution_remarque"
    )

    if st.button(
        "💾 Enregistrer",
        use_container_width=True,
        key="save_distribution"
    ):

        errors = []

        if selected_pos == "--- Sélectionner ---":
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

        if errors:

            for error in errors:
                st.error(error)

        else:

            success = append_row(
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

            if success:

                st.success(
                    "✅ Distribution enregistrée."
                )

                time.sleep(1)

                st.rerun()

    st.markdown("---")

    st.subheader(
        "📋 Derniers relevés"
    )

    if not df_distribution.empty:

        st.dataframe(
            df_distribution.tail(20),
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucun relevé enregistré."
        )


# =========================================================
# PROFIL CLIENT
# =========================================================

elif menu == "👤 Profil Client":

    st.header(
        "👤 Profil Client"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_profile = load_sheet(
        SHEET_PROFILE
    )

    st.info(
        "Si le POS existe, sélectionnez-le pour "
        "consulter/modifier son profil."
    )

    tab_existing, tab_new = st.tabs(
        [
            "🔎 POS existant",
            "➕ Nouveau POS"
        ]
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
                + unique_sorted(
                    df_pos,
                    "ID_POS"
                ),
                key="profile_existing_pos"
            )

            if selected_pos != "--- Sélectionner ---":

                existing = pd.DataFrame()

                if (
                    not df_profile.empty
                    and "ID_POS"
                    in df_profile.columns
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
                        "✅ Profil existant trouvé."
                    )

                else:

                    st.info(
                        "ℹ️ Profil détaillé non renseigné."
                    )

                with st.form(
                    "profile_form"
                ):

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
                                    pos_row.get(
                                        "Nom",
                                        ""
                                    )
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        wilaya = st.text_input(
                            "Wilaya",
                            value=clean_text(
                                pos_row.get(
                                    "Wilaya",
                                    ""
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        commune = st.text_input(
                            "Commune",
                            value=clean_text(
                                pos_row.get(
                                    "Commune",
                                    ""
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        adresse = st.text_area(
                            "Adresse",
                            value=clean_text(
                                pos_row.get(
                                    "Adresse",
                                    ""
                                )
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
                                    pos_row.get(
                                        "Téléphone",
                                        ""
                                    )
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        email = st.text_input(
                            "Email",
                            value=clean_text(
                                pos_row.get(
                                    "Email",
                                    ""
                                )
                                if pos_row is not None
                                else ""
                            )
                        )

                        current_status = clean_text(
                            pos_row.get(
                                "Statut",
                                "Actif"
                            )
                            if pos_row is not None
                            else "Actif"
                        )

                        statut = st.selectbox(
                            "Statut",
                            [
                                "Actif",
                                "Inactif"
                            ],
                            index=(
                                1
                                if current_status.lower()
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
                            [
                                "Oui",
                                "Non"
                            ],
                            index=(
                                0
                                if digital_value.lower()
                                in [
                                    "oui",
                                    "true",
                                    "1"
                                ]
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

                    # -------------------------------------------------
                    # Mise à jour POS
                    # -------------------------------------------------

                    try:

                        ws = get_ws(
                            SHEET_POS
                        )

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

                            if (
                                clean_text(
                                    row.get(
                                        "ID_POS",
                                        ""
                                    )
                                )
                                == selected_pos
                            ):

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

                                values.update(
                                    aliases
                                )

                                newrow = [
                                    values.get(
                                        h,
                                        ""
                                    )
                                    for h in headers
                                ]

                                ws.update(
                                    f"A{idx}",
                                    [
                                        newrow
                                    ]
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

                        clear_sheet_cache(
                            SHEET_POS
                        )

                        # -------------------------------------------------
                        # Profil
                        # -------------------------------------------------

                        append_dict_row(
                            SHEET_PROFILE,
                            {
                                "ID_Profil": str(
                                    uuid.uuid4()
                                ),
                                "ID": str(
                                    uuid.uuid4()
                                ),
                                "ID_POS": selected_pos,
                                "Date": str(
                                    datetime.now().date()
                                ),
                                "Date_Mise_A_Jour": str(
                                    datetime.now()
                                ),
                                "Nom_Proprietaire":
                                    nom_proprietaire,
                                "Proprietaire":
                                    nom_proprietaire,
                                "Contact_Proprietaire":
                                    contact_proprietaire,
                                "Nom_Facade":
                                    nom_facade,
                                "Nom_Acheteur":
                                    nom_acheteur,
                                "Acheteur":
                                    nom_acheteur,
                                "Contact_Acheteur":
                                    contact_acheteur,
                                "Surface_Magasin":
                                    surface,
                                "Surface":
                                    surface,
                                "Surface_Exposition":
                                    surface_expo,
                                "Nombre_Vitrines":
                                    vitrines,
                                "Vitrines":
                                    vitrines,
                                "Nombre_Travailleurs":
                                    travailleurs,
                                "Travailleurs":
                                    travailleurs,
                                "Presence_Digitale":
                                    digital == "Oui",
                                "Présence_Digitale":
                                    digital == "Oui",
                                "CA_2025":
                                    ca_2025,
                                "Observation":
                                    observation,
                                "Remarque":
                                    observation,
                                "ID_User":
                                    st.session_state.user_id
                            }
                        )

                        st.success(
                            "✅ Profil enregistré avec succès."
                        )

                        time.sleep(1)

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"❌ Erreur : {e}"
                        )

    # -----------------------------------------------------
    # NOUVEAU POS
    # -----------------------------------------------------

    with tab_new:

        with st.form(
            "new_pos_form"
        ):

            st.subheader(
                "➕ Nouveau POS"
            )

            c1, c2 = st.columns(2)

            with c1:

                new_id = st.text_input(
                    "ID_POS *",
                    value=(
                        "POS-"
                        + str(uuid.uuid4())[:8]
                        .upper()
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
                    [
                        "Actif",
                        "Inactif"
                    ]
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
                    [
                        "Oui",
                        "Non"
                    ]
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

            if (
                new_id.strip()
                in unique_sorted(
                    df_pos,
                    "ID_POS"
                )
            ):
                errors.append(
                    "Cet ID_POS existe déjà."
                )

            if errors:

                for e in errors:
                    st.error(e)

            else:

                success1 = append_dict_row(
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
                        "Date_Creation":
                            str(
                                datetime.now().date()
                            )
                    }
                )

                if success1:

                    append_dict_row(
                        SHEET_PROFILE,
                        {
                            "ID_Profil": str(
                                uuid.uuid4()
                            ),
                            "ID": str(
                                uuid.uuid4()
                            ),
                            "ID_POS":
                                new_id.strip(),
                            "Date":
                                str(
                                    datetime.now().date()
                                ),
                            "Date_Mise_A_Jour":
                                str(
                                    datetime.now()
                                ),
                            "Nom_Proprietaire":
                                p_nom,
                            "Proprietaire":
                                p_nom,
                            "Contact_Proprietaire":
                                p_contact,
                            "Nom_Facade":
                                p_facade,
                            "Nom_Acheteur":
                                p_acheteur,
                            "Acheteur":
                                p_acheteur,
                            "Contact_Acheteur":
                                p_acheteur_contact,
                            "Surface_Magasin":
                                p_surface,
                            "Surface":
                                p_surface,
                            "Surface_Exposition":
                                p_expo,
                            "Nombre_Vitrines":
                                p_vitrines,
                            "Vitrines":
                                p_vitrines,
                            "Nombre_Travailleurs":
                                p_workers,
                            "Travailleurs":
                                p_workers,
                            "Presence_Digitale":
                                p_digital == "Oui",
                            "Présence_Digitale":
                                p_digital == "Oui",
                            "CA_2025":
                                p_ca,
                            "Observation":
                                p_obs,
                            "Remarque":
                                p_obs,
                            "ID_User":
                                st.session_state.user_id
                        }
                    )

                    st.success(
                        "✅ Nouveau POS et profil enregistrés."
                    )

                    time.sleep(1)

                    st.rerun()


# =========================================================
# RELEVE PRIX
# =========================================================

elif menu == "💰 Relevé Prix":

    st.header(
        "💰 Relevé Prix"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    if df_pos.empty:
        st.warning("La table POS doit être renseignée.")
        st.stop()

    # Le référentiel Produits peut être complété depuis ce module.

    date_releve = st.date_input(
        "Date du relevé",
        value=datetime.now().date(),
        key="price_date"
    )

    # Les POS proposés proviennent exclusivement du planning de l'utilisateur.
    df_visits_price = load_sheet(SHEET_VISITS)

    pos_names = get_user_planned_pos(
        df_visits_price,
        date_releve,
        st.session_state.user_id,
        "PRIX"
    )

    if not pos_names:
        st.warning(
            "Aucun POS n'est planifié pour votre utilisateur à cette date "
            "dans le tableau Visites POS."
        )
        st.stop()

    st.subheader("🗓️ Mon planning des visites")
    st.caption(
        f"{len(pos_names)} POS prévu(s) pour le {date_releve.strftime('%d/%m/%Y')}. "
        "Cette liste correspond uniquement à votre planning personnel."
    )
    st.dataframe(
        build_planned_pos_table(
            df_pos, pos_names, df_visits_price,
            st.session_state.user_id, date_releve, "PRIX"
        ),
        use_container_width=True,
        hide_index=True
    )

    if st.session_state.get("price_pos") not in ["--- Sélectionner ---"] + pos_names:
        st.session_state["price_pos"] = "--- Sélectionner ---"

    pos = st.selectbox(
        "📍 Point de vente prévu pour cette visite",
        ["--- Sélectionner ---"] + pos_names,
        key="price_pos"
    )

    price_tournee_open = render_visit_tournee(
        df_visits_price, pos, date_releve,
        st.session_state.user_id, "price", "PRIX"
    )
    if not price_tournee_open:
        st.info("Démarrez la tournée du POS sélectionné pour commencer la saisie. Vous pourrez enregistrer plusieurs relevés avant de la clôturer.")
        st.stop()

    (
        marque,
        categorie,
        famille,
        produit,
        capacite
    ) = product_cascade(
        df_products,
        prefix="price",
        allow_add=True
    )

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
            [
                "Non",
                "Oui"
            ],
            key="price_promo"
        )

    prix_promo = st.number_input(
        "Prix promotionnel",
        min_value=0.0,
        step=100.0,
        key="price_promo_value"
    )

    remarque = st.text_area(
        "Remarque",
        key="price_remarque"
    )

    if st.button(
        "💾 Enregistrer le prix",
        use_container_width=True,
        key="save_price"
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

            success = append_row(
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
                    (
                        prix_promo
                        if promo == "Oui"
                        else 0
                    ),
                    promo == "Oui",
                    remarque,
                    st.session_state.user_id
                ]
            )

            if success:

                st.success(
                    "✅ Relevé prix enregistré."
                )

                time.sleep(1)

                st.rerun()


# =========================================================
# ENQUETE
# =========================================================

elif menu == "📝 Enquête":

    st.header(
        "📝 Enquête"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    df_subjects = load_sheet(
        SHEET_SURVEY_SUBJECTS
    )

    if (
        df_pos.empty
        or df_products.empty
    ):

        st.warning(
            "Les tables POS et Produits "
            "doivent être renseignées."
        )

        st.stop()

    if df_subjects.empty:

        st.warning(
            "Aucun sujet d'enquête disponible."
        )

        st.stop()

    sujet = st.selectbox(
        "Sujet de l'enquête",
        ["--- Sélectionner ---"]
        + unique_sorted(
            df_subjects,
            "Nom_Enquete"
        ),
        key="survey_subject"
    )

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

    marques_exposees = st.multiselect(
        "Marques exposées",
        unique_sorted(
            df_products,
            "Marque"
        ),
        key="survey_exposed_brands"
    )

    (
        marque,
        categorie,
        famille,
        produit,
        capacite
    ) = product_cascade(
        df_products,
        prefix="survey"
    )

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
            [
                "Oui",
                "Non"
            ],
            key="survey_stock"
        )

    with col2:

        promo = st.selectbox(
            "En promotion ?",
            [
                "Oui",
                "Non"
            ],
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
        key="save_survey"
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

            success = append_row(
                SHEET_SURVEYS,
                [
                    str(uuid.uuid4()),
                    str(datetime.now().date()),
                    sujet,
                    pos,
                    ", ".join(
                        marques_exposees
                    ),
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

            if success:

                st.success(
                    "✅ Enquête enregistrée."
                )

                time.sleep(1)

                st.rerun()


# =========================================================
# MATERIEL POS
# =========================================================

elif menu == "🧰 Matériel POS":

    st.header(
        "🧰 Gestion du matériel installé dans les POS"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    df_material_types = load_sheet(
        SHEET_MATERIAL_TYPES
    )

    df_material_pos = load_sheet(
        SHEET_MATERIAL_POS
    )

    df_material_control = load_sheet(
        SHEET_MATERIAL_CONTROL
    )

    # Correction : la partie Contrôle du matériel utilise aussi
    # les données de Distribution pour vérifier la conformité de la
    # marque du matériel avec les produits présents dans le POS.
    # Il faut donc charger df_distribution dans ce module également.
    df_distribution = load_sheet(
        SHEET_DISTRIBUTION
    )

    # Planning obligatoire : l'utilisateur ne peut travailler que sur
    # les POS qui lui sont affectés pour l'activité Matériel POS.
    material_date = st.date_input(
        "Date de l'activité",
        value=datetime.now().date(),
        key="material_activity_date"
    )
    df_material_visits = load_sheet(SHEET_VISITS)
    material_pos_ids = get_user_planned_pos(
        df_material_visits, material_date, st.session_state.user_id, "MATERIEL_POS"
    )
    if not material_pos_ids:
        st.warning("Aucun POS ne vous est affecté pour l'activité Matériel POS à cette date. Contactez votre responsable pour être planifié.")
        st.stop()

    st.subheader("🗓️ Mon planning — Matériel POS")
    st.dataframe(
        build_planned_pos_table(
            df_pos, material_pos_ids, df_material_visits,
            st.session_state.user_id, material_date, "MATERIEL_POS"
        ),
        use_container_width=True,
        hide_index=True
    )
    selected_material_pos = st.selectbox(
        "Point de vente prévu",
        ["--- Sélectionner ---"] + material_pos_ids,
        key="material_planned_pos"
    )
    material_tournee_open = render_visit_tournee(
        df_material_visits, selected_material_pos, material_date,
        st.session_state.user_id, "material_activity", "MATERIEL_POS"
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

        if not material_tournee_open:
            st.info("Démarrez la tournée Matériel POS depuis votre planning avant d'enregistrer une installation.")

        elif df_pos.empty:

            st.warning(
                "La table POS est vide."
            )

        elif df_material_types.empty:

            st.warning(
                "La table Types_Materiel est vide."
            )

        else:

            pos = selected_material_pos
            st.info(f"POS sélectionné depuis le planning : **{pos}**")

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
                    [
                        "Oui",
                        "Non"
                    ]
                )

            emplacement = st.text_input(
                "Emplacement"
            )

            photo = st.file_uploader(
                "Photo du matériel",
                type=[
                    "jpg",
                    "jpeg",
                    "png"
                ]
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

                    photo_url = ""
                    if photo is not None:
                        with st.spinner("📤 Envoi de la photo vers Google Drive..."):
                            photo_url = upload_photo_to_drive(
                                photo,
                                prefix="materiel"
                            )

                        if not photo_url:
                            st.error(
                                "❌ La photo n'a pas pu être enregistrée. "
                                "Le matériel n'a pas été ajouté."
                            )
                            st.stop()

                    success = append_dict_row(
                        SHEET_MATERIAL_POS,
                        {
                            "ID_Materiel":
                                str(uuid.uuid4()),
                            "ID":
                                str(uuid.uuid4()),
                            "Date_Installation":
                                str(date_install),
                            "Date":
                                str(date_install),
                            "ID_POS":
                                pos,
                            "ID_Type_Materiel":
                                clean_text(
                                    type_row.get(
                                        "ID_Type_Materiel",
                                        ""
                                    )
                                    if type_row is not None
                                    else ""
                                ),
                            "Type_Materiel":
                                type_mat,
                            "Categorie_Materiel":
                                categorie_mat,
                            "Catégorie_Materiel":
                                categorie_mat,
                            "Marque_Materiel":
                                marque_mat,
                            "Reference_Materiel":
                                reference,
                            "Référence_Materiel":
                                reference,
                            "Quantite":
                                quantite,
                            "Quantité":
                                quantite,
                            "Etat":
                                etat,
                            "Fonctionnel":
                                fonctionnel == "Oui",
                            "Emplacement":
                                emplacement,
                            "Photo":
                                photo_url,
                            "Observation":
                                observation,
                            "ID_User":
                                st.session_state.user_id
                        }
                    )

                    if success:

                        st.success(
                            "✅ Matériel enregistré."
                        )

                        time.sleep(1)

                        st.rerun()

    # -----------------------------------------------------
    # CONTROLE
    # -----------------------------------------------------

    with tab_control:

        if not material_tournee_open:
            st.info("Démarrez la tournée Matériel POS depuis votre planning avant d'effectuer un contrôle.")

        elif (
            df_pos.empty
            or df_material_pos.empty
        ):

            st.info(
                "Enregistrez d'abord un matériel."
            )

        else:

            pos_c = selected_material_pos
            st.info(f"POS à contrôler : **{pos_c}**")

            if pos_c != "--- Sélectionner ---":

                mats = df_material_pos[
                    df_material_pos[
                        "ID_POS"
                    ]
                    .astype(str)
                    .str.strip()
                    == pos_c
                ]

                if mats.empty:

                    st.info(
                        "Aucun matériel pour ce POS."
                    )

                else:

                    labels = []

                    for idx, row in mats.iterrows():

                        labels.append(
                            (
                                f'{clean_text(row.get("Type_Materiel",""))} | '
                                f'{clean_text(row.get("Marque_Materiel",""))} | '
                                f'{clean_text(row.get("ID_Materiel",row.get("ID","")))}',
                                idx
                            )
                        )

                    label = st.selectbox(
                        "Matériel",
                        [
                            x[0]
                            for x in labels
                        ],
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
                        and "Marque"
                        in df_distribution.columns
                    ):

                        d = df_distribution[
                            df_distribution[
                                "ID_POS"
                            ]
                            .astype(str)
                            .str.strip()
                            == pos_c
                        ]

                        brands = set(
                            d["Marque"]
                            .astype(str)
                            .str.strip()
                            .str.lower()
                        )

                        if brand.lower() in brands:
                            conform = "Oui"

                    st.info(
                        f"Produit de la marque "
                        f"**{brand}** présent : "
                        f"**{conform}**"
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
                            [
                                "Oui",
                                "Non"
                            ],
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
                        type=[
                            "jpg",
                            "jpeg",
                            "png"
                        ],
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

                        photo_control_url = ""
                        if photo_c is not None:
                            with st.spinner("📤 Envoi de la photo du contrôle vers Google Drive..."):
                                photo_control_url = upload_photo_to_drive(
                                    photo_c,
                                    prefix="controle_materiel"
                                )

                            if not photo_control_url:
                                st.error(
                                    "❌ La photo du contrôle n'a pas pu être enregistrée. "
                                    "Le contrôle n'a pas été enregistré."
                                )
                                st.stop()

                        success = append_dict_row(
                            SHEET_MATERIAL_CONTROL,
                            {
                                "ID_Controle":
                                    str(uuid.uuid4()),
                                "ID":
                                    str(uuid.uuid4()),
                                "Date_Controle":
                                    str(dcontrol),
                                "Date":
                                    str(dcontrol),
                                "ID_POS":
                                    pos_c,
                                "ID_Materiel":
                                    clean_text(
                                        row.get(
                                            "ID_Materiel",
                                            row.get(
                                                "ID",
                                                ""
                                            )
                                        )
                                    ),
                                "Etat":
                                    econtrol,
                                "Fonctionnel":
                                    fcontrol == "Oui",
                                "Conforme_Marque":
                                    conform == "Oui",
                                "Produit_Marque_Presente":
                                    conform == "Oui",
                                "Photo":
                                    photo_control_url,
                                "Observation":
                                    obs_c,
                                "Action_Necessaire":
                                    action,
                                "ID_User":
                                    st.session_state.user_id
                            }
                        )

                        if success:

                            st.success(
                                "✅ Contrôle enregistré."
                            )

                            time.sleep(1)

                            st.rerun()

    # -----------------------------------------------------
    # HISTORIQUE
    # -----------------------------------------------------

    with tab_history:

        st.subheader(
            "📋 Matériels installés"
        )

        material_history = df_material_pos.copy()
        if not material_history.empty and "ID_POS" in material_history.columns:
            material_history = material_history[material_history["ID_POS"].apply(clean_text).isin(material_pos_ids)]

        if not material_history.empty:

            st.dataframe(
                material_history,
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

        control_history = df_material_control.copy()
        if not control_history.empty and "ID_POS" in control_history.columns:
            control_history = control_history[control_history["ID_POS"].apply(clean_text).isin(material_pos_ids)]

        if not control_history.empty:

            st.dataframe(
                control_history,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.info(
                "Aucun contrôle enregistré."
            )


# =========================================================
# VISITES POS
# =========================================================

elif menu == "⚙️ Paramétrage des visites":

    # Sécurité : page réservée aux rôles Admin et Manager Trade.
    if normalize_role(st.session_state.role) not in {"admin", "administrateur", "administrator", "manager trade"}:
        st.error("Accès réservé aux rôles Admin et Manager Trade.")
        st.stop()

    st.header("⚙️ Paramétrage des visites")
    st.caption("Affectez une ou plusieurs activités à chaque POS, utilisateur et date : DN, Relevé des prix, Visites POS et Matériel POS. Chaque activité possède son propre statut et sa propre tournée.")

    df_pos_admin = load_sheet(SHEET_POS)
    df_users_admin = load_sheet(SHEET_USERS)
    df_visits_admin = load_sheet(SHEET_VISITS)

    if df_pos_admin.empty or "ID_POS" not in df_pos_admin.columns:
        st.warning("La feuille POS doit contenir la colonne ID_POS et des POS enregistrés.")
        st.stop()
    if df_users_admin.empty or not {"ID_User", "Nom"}.issubset(df_users_admin.columns):
        st.warning("La feuille Utilisateurs doit contenir les colonnes ID_User et Nom.")
        st.stop()

    pos_admin = df_pos_admin.copy()
    pos_admin["ID_POS"] = pos_admin["ID_POS"].apply(clean_text)
    pos_admin = pos_admin[pos_admin["ID_POS"] != ""].drop_duplicates(subset=["ID_POS"])
    users_admin = df_users_admin.copy()
    users_admin["ID_User"] = users_admin["ID_User"].apply(clean_text)
    users_admin["Nom"] = users_admin["Nom"].apply(clean_text)
    if "Statut" in users_admin.columns:
        users_admin = users_admin[users_admin["Statut"].apply(clean_text).str.lower() != "inactif"]
    users_admin = users_admin[(users_admin["ID_User"] != "") & (users_admin["Nom"] != "")].drop_duplicates(subset=["ID_User"])

    if pos_admin.empty or users_admin.empty:
        st.warning("Aucun POS ou utilisateur actif disponible pour le paramétrage.")
        st.stop()

    def pos_label(row):
        name = clean_text(row.get("Nom_POS", row.get("Nom", "")))
        return f"{row['ID_POS']} - {name}" if name else row["ID_POS"]

    pos_options = {pos_label(row): row["ID_POS"] for _, row in pos_admin.iterrows()}
    user_options = {f"{row['Nom']} ({row['ID_User']})": row["ID_User"] for _, row in users_admin.iterrows()}

    tab_add_plan, tab_view_plan = st.tabs(["➕ Nouvelle affectation", "📅 Planning des visites"])

    with tab_add_plan:
        with st.form("admin_visit_assignment_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                selected_pos_label = st.selectbox("Point de vente (POS)", list(pos_options.keys()))
                selected_user_label = st.selectbox("Utilisateur responsable", list(user_options.keys()))
            with c2:
                planned_date = st.date_input("Date prévue de visite", value=datetime.now().date(), key="admin_planned_visit_date")
                activity_options = ["DN", "PRIX", "VISITES_POS", "MATERIEL_POS"]
                selected_types = st.multiselect(
                    "Activité(s) à réaliser",
                    options=activity_options,
                    default=["DN", "PRIX"],
                    format_func=visit_type_label
                )
            save_assignment = st.form_submit_button("💾 Enregistrer l'affectation", use_container_width=True)

        if save_assignment:
            selected_pos_id = pos_options[selected_pos_label]
            selected_user_id = user_options[selected_user_label]
            if not selected_types:
                st.error("Sélectionnez au moins une activité à réaliser.")
            else:
                try:
                    ensure_sheet_columns(
                        SHEET_VISITS,
                        [
                            "Type_Visite", "Statut_Tournee", "Heure_Debut",
                            "Heure_Fin", "Motif_Cloture", "Observation_Cloture"
                        ]
                    )
                except Exception as exc:
                    st.error(f"Impossible de préparer les colonnes de planning : {exc}")
                    st.stop()
                existing = df_visits_admin.copy()
                date_col = "Date_Visite" if "Date_Visite" in existing.columns else ("Date" if "Date" in existing.columns else None)
                created_types = []
                duplicates = []
                for activity_type in selected_types:
                    duplicate = False
                    if not existing.empty and date_col and {"ID_POS", "ID_User"}.issubset(existing.columns):
                        check = existing.copy()
                        check["_pos"] = check["ID_POS"].apply(clean_text)
                        check["_user"] = check["ID_User"].apply(clean_text)
                        check["_date"] = pd.to_datetime(check[date_col], errors="coerce", dayfirst=True).dt.date
                        if "Type_Visite" in check.columns:
                            check["_type"] = check["Type_Visite"].apply(normalize_visit_type)
                            # Une affectation n'est un doublon que pour la même activité.
                            # Les anciennes lignes sans type restent historiques et ne bloquent pas
                            # la création des nouveaux types d'activité.
                            type_match = check["_type"] == activity_type
                        else:
                            type_match = pd.Series(False, index=check.index)
                        duplicate = ((check["_pos"] == selected_pos_id) &
                                     (check["_user"] == selected_user_id) &
                                     (check["_date"] == planned_date) & type_match).any()
                    if duplicate:
                        duplicates.append(visit_type_label(activity_type))
                        continue
                    assignment_id = str(uuid.uuid4())
                    success = append_dict_row(
                        SHEET_VISITS,
                        {
                            "ID_Visite": assignment_id,
                            "ID": assignment_id,
                            "Date_Visite": str(planned_date),
                            "Date": str(planned_date),
                            "ID_POS": selected_pos_id,
                            "ID_User": selected_user_id,
                            "Type_Visite": activity_type,
                            "Statut_Tournee": "Planifiée",
                            "Heure_Debut": "",
                            "Heure_Fin": "",
                            "Motif_Cloture": "",
                            "Observation_Cloture": "",
                            "Motif": "Planification",
                            "Resultat": "",
                            "Résultat": "",
                            "Observation": ""
                        }
                    )
                    if success:
                        created_types.append(visit_type_label(activity_type))
                        # Mettre à jour le DataFrame local pour éviter un doublon dans le même formulaire.
                        new_record = {"ID_POS": selected_pos_id, "ID_User": selected_user_id, date_col or "Date_Visite": str(planned_date), "Type_Visite": activity_type}
                        existing = pd.concat([existing, pd.DataFrame([new_record])], ignore_index=True)
                if created_types:
                    clear_sheet_cache(SHEET_VISITS)
                    st.success("Affectation(s) créée(s) : " + " et ".join(created_types) + ".")
                    st.rerun()
                if duplicates:
                    st.warning("Affectation déjà existante pour : " + " et ".join(duplicates) + ".")

    with tab_view_plan:
        if df_visits_admin.empty or not {"ID_POS", "ID_User"}.issubset(df_visits_admin.columns):
            st.info("Aucune affectation enregistrée pour le moment.")
        else:
            plan = df_visits_admin.copy()
            date_col = "Date_Visite" if "Date_Visite" in plan.columns else ("Date" if "Date" in plan.columns else None)
            if date_col:
                plan["Date prévue"] = pd.to_datetime(plan[date_col], errors="coerce", dayfirst=True).dt.date
                plan["ID_POS"] = plan["ID_POS"].apply(clean_text)
                plan["ID_User"] = plan["ID_User"].apply(clean_text)
                pos_name_map = {clean_text(row["ID_POS"]): clean_text(row.get("Nom_POS", row.get("Nom", ""))) for _, row in pos_admin.iterrows()}
                user_name_map = dict(zip(users_admin["ID_User"], users_admin["Nom"]))
                plan["Point de vente"] = plan["ID_POS"].map(lambda x: (x + " - " + pos_name_map[x]) if pos_name_map.get(x) else x)
                plan["Utilisateur"] = plan["ID_User"].map(lambda x: user_name_map.get(x, x))
                if "Type_Visite" in plan.columns:
                    plan["Type de visite"] = plan["Type_Visite"].apply(lambda x: visit_type_label(x) if normalize_visit_type(x) else "Ancienne affectation (type non précisé)")
                else:
                    plan["Type de visite"] = "Ancienne affectation (type non précisé)"
                plan["Statut"] = plan.get("Statut_Tournee", pd.Series("Planifiée", index=plan.index)).fillna("").replace("", "Planifiée")
                display_cols = [c for c in ["Date prévue", "Utilisateur", "Point de vente", "Type de visite", "Statut"] if c in plan.columns]
                st.dataframe(plan[display_cols].sort_values("Date prévue", na_position="last"), use_container_width=True, hide_index=True)
            else:
                st.warning("La feuille Visites_POS doit contenir Date_Visite ou Date pour afficher le planning.")

elif menu == "🚗 Visites POS":

    st.header("🚗 Visites POS")
    st.caption("Consultez uniquement les POS qui vous sont affectés pour une visite terrain à cette date.")

    df_pos = load_sheet(SHEET_POS)
    df_visits = load_sheet(SHEET_VISITS)

    if df_pos.empty:
        st.warning("La table POS est vide.")
        st.stop()

    date_visite = st.date_input(
        "Date de visite",
        value=datetime.now().date(),
        key="field_visit_date"
    )

    planned_pos_ids = get_user_planned_pos(
        df_visits, date_visite, st.session_state.user_id, "VISITES_POS"
    )

    if not planned_pos_ids:
        st.warning("Aucun POS ne vous est affecté pour l'activité Visites POS à cette date. Contactez votre responsable pour être planifié.")
        st.stop()

    st.subheader("🗓️ Mon planning — Visites POS")
    st.dataframe(
        build_planned_pos_table(
            df_pos, planned_pos_ids, df_visits,
            st.session_state.user_id, date_visite, "VISITES_POS"
        ),
        use_container_width=True,
        hide_index=True
    )

    pos_visit = st.selectbox(
        "Point de vente prévu",
        ["--- Sélectionner ---"] + planned_pos_ids,
        key="field_visit_pos"
    )

    visit_open = render_visit_tournee(
        df_visits, pos_visit, date_visite,
        st.session_state.user_id, "field_visit", "VISITES_POS"
    )

    if visit_open:
        st.info("La tournée Visites POS est ouverte. Après votre passage, clôturez-la en indiquant le résultat et une observation si nécessaire.")


# =========================================================
# OBJECTIFS POS
# =========================================================

elif menu == "🎯 Objectifs POS":

    st.header(
        "🎯 Objectifs POS"
    )

    df_pos = load_sheet(
        SHEET_POS
    )

    df_objectives = load_sheet(
        SHEET_OBJECTIVES
    )

    if df_pos.empty:

        st.warning(
            "La table POS est vide."
        )

        st.stop()

    st.subheader(
        "🎯 Nouvel objectif"
    )

    pos = st.selectbox(
        "Point de vente",
        ["--- Sélectionner ---"]
        + unique_sorted(
            df_pos,
            "ID_POS"
        ),
        key="objective_pos"
    )

    annee = st.number_input(
        "Année",
        min_value=2020,
        max_value=2100,
        value=datetime.now().year,
        step=1
    )

    objectif_type = st.selectbox(
        "Type d'objectif",
        [
            "CA",
            "Volume",
            "Nombre de commandes",
            "Distribution",
            "Autre"
        ]
    )

    objectif = st.number_input(
        "Objectif",
        min_value=0.0,
        step=1.0
    )

    commentaire = st.text_area(
        "Commentaire"
    )

    if st.button(
        "💾 Enregistrer l'objectif",
        use_container_width=True,
        key="save_objective"
    ):

        if pos == "--- Sélectionner ---":

            st.error(
                "Sélectionnez un POS."
            )

        elif objectif <= 0:

            st.error(
                "L'objectif doit être supérieur à 0."
            )

        else:

            success = append_dict_row(
                SHEET_OBJECTIVES,
                {
                    "ID_Objectif":
                        str(uuid.uuid4()),
                    "ID":
                        str(uuid.uuid4()),
                    "Date":
                        str(datetime.now().date()),
                    "Annee":
                        int(annee),
                    "Année":
                        int(annee),
                    "ID_POS":
                        pos,
                    "Type_Objectif":
                        objectif_type,
                    "Objectif":
                        objectif,
                    "Commentaire":
                        commentaire,
                    "ID_User":
                        st.session_state.user_id
                }
            )

            if success:

                st.success(
                    "✅ Objectif enregistré."
                )

                time.sleep(1)

                st.rerun()

    st.markdown("---")

    st.subheader(
        "📋 Objectifs enregistrés"
    )

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

    st.header(
        "📈 Statistiques"
    )

    # -----------------------------------------------------
    # Chargement uniquement des tables utiles
    # -----------------------------------------------------

    df_pos = load_sheet(
        SHEET_POS
    )

    df_products = load_sheet(
        SHEET_PRODUCTS
    )

    df_distribution = load_sheet(
        SHEET_DISTRIBUTION
    )

    df_prices = load_sheet(
        SHEET_PRICES
    )

    df_surveys = load_sheet(
        SHEET_SURVEYS
    )

    df_profile = load_sheet(
        SHEET_PROFILE
    )

    df_material_pos = load_sheet(
        SHEET_MATERIAL_POS
    )

    df_material_control = load_sheet(
        SHEET_MATERIAL_CONTROL
    )

    total_pos = len(
        df_pos
    )

    total_distribution = len(
        df_distribution
    )

    total_price = len(
        df_prices
    )

    total_surveys = len(
        df_surveys
    )

    total_material = len(
        df_material_pos
    )

    total_brands = (
        df_products["Marque"].nunique()
        if (
            not df_products.empty
            and "Marque"
            in df_products.columns
        )
        else 0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric(
        "POS",
        total_pos
    )

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
    # DISTRIBUTION
    # -----------------------------------------------------

    if not df_distribution.empty:

        st.subheader(
            "📦 Distribution par marque"
        )

        if (
            "Marque"
            in df_distribution.columns
        ):

            dist = df_distribution.copy()

            if "Quantite" in dist.columns:

                dist["Quantite"] = pd.to_numeric(
                    dist["Quantite"],
                    errors="coerce"
                ).fillna(0)

                chart = (
                    dist
                    .groupby("Marque")["Quantite"]
                    .sum()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(
                    chart
                )

            elif "Quantité" in dist.columns:

                dist["Quantité"] = pd.to_numeric(
                    dist["Quantité"],
                    errors="coerce"
                ).fillna(0)

                chart = (
                    dist
                    .groupby("Marque")["Quantité"]
                    .sum()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(
                    chart
                )

        if (
            "Catégorie"
            in df_distribution.columns
        ):

            st.subheader(
                "🏷️ Distribution par catégorie"
            )

            quantity_col = None

            if "Quantite" in df_distribution.columns:
                quantity_col = "Quantite"

            elif "Quantité" in df_distribution.columns:
                quantity_col = "Quantité"

            if quantity_col:

                temp_dist = df_distribution.copy()

                temp_dist[quantity_col] = pd.to_numeric(
                    temp_dist[quantity_col],
                    errors="coerce"
                ).fillna(0)

                chart_cat = (
                    temp_dist
                    .groupby(
                        "Catégorie"
                    )[quantity_col]
                    .sum()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(
                    chart_cat
                )

    # -----------------------------------------------------
    # PRIX
    # -----------------------------------------------------

    if not df_prices.empty:

        st.subheader(
            "💰 Analyse des prix"
        )

        price_column = None

        if "Prix_Vente" in df_prices.columns:
            price_column = "Prix_Vente"

        elif "Prix" in df_prices.columns:
            price_column = "Prix"

        if price_column:

            price_df = df_prices.copy()

            price_df[price_column] = pd.to_numeric(
                price_df[price_column],
                errors="coerce"
            )

            if "Marque" in price_df.columns:

                avg_price = (
                    price_df
                    .groupby("Marque")[
                        price_column
                    ]
                    .mean()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(
                    avg_price
                )

                price_summary = (
                    price_df
                    .groupby("Marque")
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

        if (
            "Marque"
            in df_surveys.columns
        ):

            survey_brand = (
                df_surveys["Marque"]
                .astype(str)
                .value_counts()
            )

            st.bar_chart(
                survey_brand
            )

        freq_column = None

        if (
            "Frequence_Vente_Jour"
            in df_surveys.columns
        ):

            freq_column = (
                "Frequence_Vente_Jour"
            )

        elif (
            "Fréquence_Vente_Jour"
            in df_surveys.columns
        ):

            freq_column = (
                "Fréquence_Vente_Jour"
            )

        if freq_column:

            freq_df = df_surveys.copy()

            freq_df[freq_column] = pd.to_numeric(
                freq_df[freq_column],
                errors="coerce"
            )

            if "Marque" in freq_df.columns:

                avg_freq = (
                    freq_df
                    .groupby("Marque")[
                        freq_column
                    ]
                    .mean()
                    .sort_values(
                        ascending=False
                    )
                )

                st.subheader(
                    "📊 Fréquence moyenne "
                    "de vente / jour"
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
            "Contrôles"
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
