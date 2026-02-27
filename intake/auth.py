import json
import time
import streamlit as st


def require_access(auth_cfg: dict):
    if not auth_cfg.get("enabled", True):
        return

    raw = auth_cfg.get("passcodes", "[]")
    try:
        passcodes = json.loads(raw) if isinstance(raw, str) else list(raw)
    except Exception:
        passcodes = []

    st.sidebar.header("Access")
    code = st.sidebar.text_input("Passcode", type="password", placeholder="Enter passcode")

    if not code or code not in passcodes:
        st.sidebar.error("Access denied.")
        st.stop()

    st.sidebar.success("Access granted.")
    st.sidebar.caption(f"Session: {time.strftime('%Y-%m-%d %H:%M:%S')}")
