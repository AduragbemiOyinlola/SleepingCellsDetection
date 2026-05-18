"""
Sleeping Cell Detector — Main Application Entry Point
======================================================
Run with:  streamlit run app.py
"""

import streamlit as st
from utils.auth import init_session, render_login_page, is_authenticated
from utils.styles import inject_global_styles

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SleepGuard | Sleeping Cell Detector",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_styles()
init_session()

# ─── Route ────────────────────────────────────────────────────────────────────
if not is_authenticated():
    render_login_page()
else:
    # Import here so unauthenticated users never touch pipeline code
    from pages.dashboard import render_dashboard
    render_dashboard()