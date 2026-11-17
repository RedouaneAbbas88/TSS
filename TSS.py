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

