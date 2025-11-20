# --- Authentification avec session_state ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_code_vendeur" not in st.session_state:
    st.session_state.user_code_vendeur = ""

st.sidebar.header("Connexion")
if not st.session_state.logged_in:
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
        if user_row['Password'] != password_input:  # mot de passe clair
            st.sidebar.error("Mot de passe incorrect.")
            st.stop()
        # Sauvegarder dans session_state
        st.session_state.logged_in = True
        st.session_state.user_email = email_input
        st.session_state.user_role = user_row.get('Role', 'PreVendeur')
        st.session_state.user_code_vendeur = user_row.get('Code_Vendeur', "")
        st.experimental_rerun()  # relancer pour charger l'interface
else:
    st.sidebar.success(f"Connecté : {st.session_state.user_email} — {st.session_state.user_role}")
