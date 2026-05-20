"""
utils/auth.py — Authentication & session management
=====================================================

Supports three modes (controlled by config.py / env vars):
  1. DEMO     — hardcoded credentials for local testing
  2. OAUTH    — Google OAuth 2.0 / Microsoft SSO via authlib (plug-in)
  3. LDAP     — Corporate LDAP/Active-Directory (plug-in)

The render_login_page() function handles all three modes and stores
a user dict in st.session_state["user"] on success.
"""

import streamlit as st
import hashlib
import hmac
import time
from datetime import datetime
from utils.config import (
    AUTH_MODE,
    DEMO_USERS,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_REDIRECT_URI,
    APP_NAME,
)


# ─── Session helpers ───────────────────────────────────────────────────────────

def init_session():
    """Initialise all session-state keys that the rest of the app relies on."""
    defaults = {
        "user": None,
        "email_connected": False,
        "email_credentials": {},
        "fetched_email": None,
        "parsed_sites": None,          # list[dict]  e.g. [{"cell_id": "CL001", ...}]
        "kpi_data": None,              # dict  cell_id -> DataFrame
        "plots": None,                 # dict  cell_id -> {"cs": Figure, "ps": Figure}
        "classifications": None,       # dict  cell_id -> {"cs": int, "ps": int, "final": int}
        "report_csv": None,            # bytes
        "report_sent": False,
        "pipeline_log": [],
        "pipeline_step": 0,            # 0-5
        "run_ts": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def is_authenticated() -> bool:
    return st.session_state.get("user") is not None


def get_user() -> dict:
    return st.session_state.get("user", {})


def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _verify_demo(username: str, password: str):
    """Return user dict or None."""
    for u in DEMO_USERS:
        if u["username"].lower() == username.lower():
            if hmac.compare_digest(_hash_pw(password), _hash_pw(u["password"])):
                return {
                    "username": u["username"],
                    "display_name": u.get("display_name", u["username"]),
                    "email": u.get("email", ""),
                    "role": u.get("role", "engineer"),
                    "login_ts": datetime.utcnow().isoformat(),
                }
    return None


# ─── Login UI ──────────────────────────────────────────────────────────────────

def render_login_page():
    """Full-page login form rendered when the user is not authenticated."""

    # Centered column layout
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        st.markdown("""
        <div style="text-align:center; padding: 2.5rem 0 1.5rem;">
          <div style="font-family:'Space Mono',monospace; font-size:2rem;
                      color:var(--accent); letter-spacing:-0.02em;">
            📡 SleepGuard
          </div>
          <div style="color:var(--muted); font-size:0.85rem; margin-top:0.3rem;">
            Automated Sleeping Cell Detection System
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="h-line">', unsafe_allow_html=True)

        if AUTH_MODE == "DEMO":
            _render_demo_login()
        elif AUTH_MODE == "OAUTH":
            _render_oauth_login()
        else:
            st.error(f"Unknown AUTH_MODE='{AUTH_MODE}' in config.py")

        st.markdown("""
        <div style="text-align:center; color:var(--muted); font-size:0.72rem;
                    margin-top:2rem; font-family:'Space Mono',monospace;">
          © 2025 SleepGuard &nbsp;|&nbsp; Telecom Network Operations
        </div>
        """, unsafe_allow_html=True)


def _render_demo_login():
    st.markdown("""
    <div style="background:rgba(255,209,102,0.08); border:1px solid rgba(255,209,102,0.25);
                border-radius:6px; padding:0.6rem 1rem; margin-bottom:1rem;
                font-size:0.78rem; color:var(--warning);">
      ⚠️  Demo mode — use any credentials from <code>config.py → DEMO_USERS</code>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Username", placeholder="e.g. engineer1")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign In →", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Please enter both username and password.")
            return
        with st.spinner("Authenticating…"):
            time.sleep(0.4)          # simulate network round-trip
            user = _verify_demo(username, password)
        if user:
            st.session_state["user"] = user
            st.success(f"Welcome, {user['display_name']}!")
            time.sleep(0.5)
            st.rerun()
        else:
            st.error("Invalid credentials. Please try again.")

    # Show available demo accounts
    with st.expander("Available demo accounts"):
        for u in DEMO_USERS:
            st.code(f"username: {u['username']}   password: {u['password']}")


def _render_oauth_login():
    """
    Google OAuth 2.0 / Microsoft SSO stub.

    To activate, install:  pip install authlib requests
    Then fill in OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET in config.py.

    The flow below follows the standard Authorization-Code pattern.
    In production, deploy behind HTTPS and store tokens in a secure backend.
    """
    st.info(
        "OAuth 2.0 / SSO is configured. Click the button below to authenticate "
        "with your corporate identity provider."
    )

    # Build the authorization URL
    try:
        from authlib.integrations.requests_client import OAuth2Session

        provider_url = "https://accounts.google.com/o/oauth2/v2/auth"  # swap for MS/Okta
        scope = "openid email profile"

        oauth = OAuth2Session(
            client_id=OAUTH_CLIENT_ID,
            redirect_uri=OAUTH_REDIRECT_URI,
            scope=scope,
            response_type="code",
        )
        auth_url, state = oauth.create_authorization_url(provider_url)
        st.session_state["oauth_state"] = state

        st.markdown(
            f'<a href="{auth_url}" target="_self">'
            '<button style="width:100%;padding:0.6rem;background:var(--accent);'
            'color:#000;border:none;border-radius:4px;font-weight:700;cursor:pointer;">'
            '🔐 Sign in with Corporate SSO</button></a>',
            unsafe_allow_html=True,
        )

        # Handle callback (query params contain code & state)
        params = st.query_params
        if "code" in params:
            code  = params["code"]
            state = params.get("state", "")
            token_url = "https://oauth2.googleapis.com/token"
            token = oauth.fetch_token(
                token_url,
                code=code,
                client_secret=OAUTH_CLIENT_SECRET,
            )
            userinfo = oauth.get("https://www.googleapis.com/oauth2/v3/userinfo").json()
            # print("OAuth login successful. User info:", userinfo)
            st.session_state["user"] = {
                "username":     userinfo.get("email", ""),
                "display_name": userinfo.get("name", ""),
                "email":        userinfo.get("email", ""),
                "role":         "engineer",
                "login_ts":     datetime.utcnow().isoformat(),
                "oauth_token":  token,
            }
            st.query_params.clear()
            st.rerun()

    except ImportError:
        st.warning(
            "authlib not installed. Run:  `pip install authlib requests`  "
            "then restart the app, or switch to AUTH_MODE='DEMO' in config.py."
        )