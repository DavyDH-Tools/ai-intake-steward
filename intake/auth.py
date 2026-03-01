import json
import streamlit as st


def require_access(auth_cfg: dict):
    if not auth_cfg.get("enabled", True):
        st.session_state.is_admin = True
        return

    # Fast path: already authenticated this session — skip the form entirely.
    if st.session_state.get("_auth_ok"):
        return

    raw = auth_cfg.get("passcodes", "[]")
    try:
        passcodes = json.loads(raw) if isinstance(raw, str) else list(raw)
    except Exception:
        passcodes = []

    admin_code = auth_cfg.get("admin_code", "")

    with st.sidebar.form("_auth_form", clear_on_submit=False):
        st.markdown("**Access required**")
        code = st.text_input(
            "Access code",
            type="password",
            placeholder="Enter access code",
        )
        submitted = st.form_submit_button(
            "Unlock", use_container_width=True, type="primary"
        )

    if not submitted:
        # Nothing submitted yet — show a neutral prompt, don't show any error.
        st.stop()

    if code not in passcodes:
        st.sidebar.error("Incorrect access code. Please try again.")
        st.stop()

    # Correct — cache in session state and rerun cleanly without the auth form.
    st.session_state._auth_ok = True
    st.session_state.is_admin = bool(admin_code and code == admin_code)
    st.rerun()
