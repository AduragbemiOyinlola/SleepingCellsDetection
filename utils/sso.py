"""
utils/sso.py — unified single sign-in (email -> detect provider -> OAuth)
=========================================================================
The user types their e-mail and clicks CONTINUE. We detect Google vs Microsoft
(utils/provider_detect.py) and redirect straight into that provider's OAuth
consent. One consent logs the user in AND connects their mailbox.

State across the redirect
-------------------------
The provider redirect (…/?code=&state=) is a FULL PAGE RELOAD, which wipes
st.session_state. So the chosen provider and the OAuth flow context are kept in
a module-level dict (_OAUTH_CACHE) that lives in the Streamlit SERVER PROCESS
and survives reloads, keyed by the OAuth `state`.

Token refresh
-------------
OAuth access tokens are short-lived; without refresh you get "HTTP 401" partway
through the pipeline. We persist refresh material (MSAL token cache for
Microsoft, the authorized-user JSON for Google) in session_state and register a
refresher with utils/email_client.py, which calls it on a 401 to get a fresh
token and retry.
"""

from __future__ import annotations

import os
import json
import secrets
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

import utils.config as cfg
import utils.email_client as email_client
from utils.config import (
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GMAIL_OAUTH_SCOPES,
    MS_CLIENT_ID, MS_TENANT, MS_CLIENT_SECRET, MS_OAUTH_SCOPES,
    EMAIL_REDIRECT_URI,
)
from utils.provider_detect import detect_provider

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# state -> {"provider", "ms_flow"?}  (survives page reloads; in-process)
_OAUTH_CACHE: dict[str, dict] = {}


# Refresh material (Google authorized-user JSON / MSAL token cache) is stored in
# st.session_state — NOT a module global — so it survives Streamlit reruns AND
# the module re-imports that happen when a source file is edited mid-session.
def _store_refresh(provider: str, material: dict) -> None:
    st.session_state.setdefault("_oauth_refresh", {})[provider] = material


def _load_refresh(provider: str) -> dict | None:
    return st.session_state.get("_oauth_refresh", {}).get(provider)


def _current_provider() -> str | None:
    creds = st.session_state.get("email_credentials") or {}
    return creds.get("provider")


# ─── Google ───────────────────────────────────────────────────────────────────

def _google_client_config():
    return {"web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [EMAIL_REDIRECT_URI],
    }}


def _google_auth_url() -> str:
    from google_auth_oauthlib.flow import Flow
    state = secrets.token_urlsafe(16)
    flow = Flow.from_client_config(_google_client_config(), scopes=GMAIL_OAUTH_SCOPES)
    flow.redirect_uri = EMAIL_REDIRECT_URI
    url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true",
                                    prompt="consent", state=state)
    _OAUTH_CACHE[state] = {"provider": "gmail"}
    return url


def _google_exchange(code: str) -> dict:
    from google_auth_oauthlib.flow import Flow
    import requests
    flow = Flow.from_client_config(_google_client_config(), scopes=GMAIL_OAUTH_SCOPES)
    flow.redirect_uri = EMAIL_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials
    _store_refresh("gmail", {"google_creds": creds.to_json()})   # includes refresh_token

    # Verify the mailbox-read scope was actually granted (not just requested).
    ti = requests.get("https://oauth2.googleapis.com/tokeninfo",
                      params={"access_token": creds.token}, timeout=15)
    granted = ti.json().get("scope", "") if ti.status_code == 200 else ""
    if "gmail.readonly" not in granted.lower():
        raise RuntimeError(
            "Signed in, but Gmail did NOT grant mailbox-read access "
            "(gmail.readonly). Your Google OAuth app must add the Gmail API "
            "scopes on the consent screen and you must approve them. "
            f"Granted scopes: {granted or '(none)'}")

    info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                        headers={"Authorization": f"Bearer {creds.token}"}, timeout=15).json()
    return {"token": creds.token, "email": info.get("email", ""),
            "name": info.get("name", info.get("email", "")), "scopes": granted}


def _google_refresh() -> str | None:
    mat = _load_refresh("gmail")
    if not mat:
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_info(json.loads(mat["google_creds"]), GMAIL_OAUTH_SCOPES)
    if not creds.refresh_token:
        return None
    creds.refresh(Request())
    _store_refresh("gmail", {"google_creds": creds.to_json()})
    return creds.token


# ─── Microsoft ────────────────────────────────────────────────────────────────

def _ms_app(cache_blob: str | None = None):
    import msal
    cache = msal.SerializableTokenCache()
    if cache_blob:
        cache.deserialize(cache_blob)
    authority = f"https://login.microsoftonline.com/{MS_TENANT}"
    if MS_CLIENT_SECRET:
        app = msal.ConfidentialClientApplication(
            MS_CLIENT_ID, authority=authority,
            client_credential=MS_CLIENT_SECRET, token_cache=cache)
    else:
        app = msal.PublicClientApplication(MS_CLIENT_ID, authority=authority, token_cache=cache)
    return app, cache


def _ms_auth_url() -> str:
    app, _ = _ms_app()
    flow = app.initiate_auth_code_flow(MS_OAUTH_SCOPES, redirect_uri=EMAIL_REDIRECT_URI)
    _OAUTH_CACHE[flow["state"]] = {"provider": "outlook", "ms_flow": flow}
    return flow["auth_uri"]


def _ms_exchange(ms_flow: dict, auth_response: dict) -> dict:
    import requests
    app, cache = _ms_app()
    result = app.acquire_token_by_auth_code_flow(ms_flow, auth_response)
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "MS token exchange failed"))
    _store_refresh("outlook", {"ms_cache": cache.serialize()})   # holds the refresh token

    granted = result.get("scope", "")
    if "Mail.Read" not in granted:
        raise RuntimeError(
            "Signed in, but Microsoft did NOT grant mailbox-read access "
            "(Mail.Read). Your Azure app registration must add Microsoft Graph "
            "DELEGATED permissions Mail.Read + Mail.Send (with admin consent if "
            f"required). Granted scopes: {granted or '(none)'}")

    me = requests.get("https://graph.microsoft.com/v1.0/me",
                      headers={"Authorization": f"Bearer {result['access_token']}"}, timeout=15).json()
    return {"token": result["access_token"],
            "email": me.get("mail") or me.get("userPrincipalName", ""),
            "name": me.get("displayName", ""), "scopes": granted}


def _ms_refresh() -> str | None:
    mat = _load_refresh("outlook")
    if not mat:
        return None
    app, cache = _ms_app(cache_blob=mat["ms_cache"])
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(MS_OAUTH_SCOPES, account=accounts[0])
    if not result or "access_token" not in result:
        return None
    _store_refresh("outlook", {"ms_cache": cache.serialize()})
    return result["access_token"]


# ─── refresher hook (called by email_client on a 401) ─────────────────────────

def _refresh_token(provider: str) -> str | None:
    token = _google_refresh() if provider == "gmail" else _ms_refresh()
    if token:
        creds = st.session_state.get("email_credentials")
        if creds:
            creds["password"] = token        # keep the session token current
    return token


email_client.set_token_refresher(_refresh_token)
email_client.set_provider_getter(_current_provider)


# ─── session wiring ───────────────────────────────────────────────────────────

def _finalise_login(provider: str, info: dict):
    cfg.EMAIL_PROVIDER = provider
    email_client.set_active_provider(provider)   # bind routing to this account
    st.session_state["user"] = {
        "username": info["email"], "display_name": info["name"] or info["email"],
        "email": info["email"], "role": "engineer",
        "login_ts": datetime.utcnow().isoformat(), "provider": provider,
    }
    st.session_state["email_connected"] = True
    st.session_state["email_credentials"] = {
        "email_address": info["email"], "password": info["token"], "provider": provider,
    }
    st.session_state["pipeline_step"] = max(st.session_state.get("pipeline_step", 0), 1)


def _handle_callback() -> bool:
    params = st.query_params
    if "code" not in params:
        return False
    ctx = _OAUTH_CACHE.pop(params.get("state", ""), None)
    try:
        if ctx is None:
            raise RuntimeError("sign-in session expired — please try again.")
        info = (_google_exchange(params["code"]) if ctx["provider"] == "gmail"
                else _ms_exchange(ctx["ms_flow"], dict(params)))
        _finalise_login(ctx["provider"], info)
        st.query_params.clear()
        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"Sign-in failed: {e}")
        st.query_params.clear()
    return True


# ─── UI ───────────────────────────────────────────────────────────────────────

def _auth_url_for(provider: str) -> str:
    return _google_auth_url() if provider == "gmail" else _ms_auth_url()


def _redirect(url: str):
    components.html(f"<script>window.top.location.href = {url!r};</script>", height=0)
    st.caption("Redirecting to secure sign-in…")
    st.markdown(f"<a href='{url}' target='_self' style='font-size:0.8rem;'>"
                "If you are not redirected automatically, click here.</a>",
                unsafe_allow_html=True)


def render_unified_login():
    if _handle_callback():
        return
    if st.session_state.get("sso_redirect_url"):
        _redirect(st.session_state.pop("sso_redirect_url"))
        return

    st.markdown("#### Sign in to NOC")
    st.caption("Access the sleeping cell detection platform")

    email = st.text_input("Email address", placeholder="engineer@network.ng", key="sso_email")
    if st.button("CONTINUE →", use_container_width=True):
        if not email or "@" not in email:
            st.error("Enter a valid e-mail address.")
            return
        with st.spinner("Detecting your mail provider…"):
            provider, _ = detect_provider(email)
        if provider == "unknown":
            st.session_state["sso_unknown"] = True
        else:
            st.session_state["sso_redirect_url"] = _auth_url_for(provider)
        st.rerun()

    if st.session_state.get("sso_unknown"):
        choice = st.radio("We couldn't detect your provider. Choose it:",
                          ["Google / Gmail", "Microsoft / Outlook"], horizontal=True)
        if st.button("Proceed →", use_container_width=True):
            provider = "gmail" if "Google" in choice else "outlook"
            st.session_state.pop("sso_unknown", None)
            st.session_state["sso_redirect_url"] = _auth_url_for(provider)
            st.rerun()