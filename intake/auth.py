import json
from typing import Optional

import streamlit as st


def require_access(auth_cfg: dict) -> Optional[str]:
    """Enforce passcode gate.

    Returns the email address associated with the authenticated code (may be
    None if the passcode list doesn't carry email mappings), or returns the
    cached value if the session is already authenticated.

    Calls st.stop() when access is denied or the form has not been submitted.

    PASSCODES_JSON formats supported:
      list  — ["code1", "code2"]                  (no email lookup)
      dict  — {"code1": "alice@example.com", …}   (auto-fills member email)
    """
    if not auth_cfg.get("enabled", True):
        st.session_state.is_admin = True
        return None

    # Fast path: already authenticated this session — skip the form entirely.
    if st.session_state.get("_auth_ok"):
        return st.session_state.get("_auth_email")

    raw = auth_cfg.get("passcodes", "[]")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        parsed = []

    # Normalise to a dict of {code: email_or_None}
    if isinstance(parsed, dict):
        code_map: dict = {str(k): str(v) for k, v in parsed.items()}
    else:
        code_map = {str(c): None for c in parsed}

    admin_code = auth_cfg.get("admin_code", "")
    admin_email = auth_cfg.get("admin_email", "")

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
        st.stop()

    if code not in code_map:
        st.sidebar.error("Incorrect access code. Please try again.")
        st.stop()

    email: Optional[str] = code_map[code]
    is_admin = bool(admin_code and code == admin_code)
    if is_admin and not email:
        email = admin_email or None

    st.session_state._auth_ok = True
    st.session_state._auth_email = email
    st.session_state.is_admin = is_admin
    st.rerun()
