"""
utils/config.py — Central configuration
========================================
Prefer environment variables for secrets in production.
Fallback defaults are provided for local/demo usage.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Auth ─────────────────────────────────────────────────────────────────────
# "DEMO" | "OAUTH"
AUTH_MODE = os.getenv("AUTH_MODE", "OAUTH")

APP_NAME = "SleepGuard"

# Demo credentials (never use in production)
DEMO_USERS = [
    {
        "username": "engineer1",
        "password": "test1234",
        "display_name": "Oyinlola Aduragbemi",
        "email": "engineer1@telecom.ng",
        "role": "engineer",
    },
    {
        "username": "admin",
        "password": "admin1234",
        "display_name": "Admin User",
        "email": "admin@telecom.ng",
        "role": "admin",
    },
]

# OAuth (Google / Microsoft / Okta)
OAUTH_CLIENT_ID     = os.getenv("OAUTH_CLIENT_ID",     "CLIENT_ID")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "CLIENT_SECRET")
OAUTH_REDIRECT_URI  = os.getenv("OAUTH_REDIRECT_URI",  "http://localhost:8501/")

# ─── Email ────────────────────────────────────────────────────────────────────
# Supported providers: "gmail" | "outlook"
EMAIL_PROVIDER       = os.getenv("EMAIL_PROVIDER",       "gmail")
IMAP_HOST_GMAIL      = "imap.gmail.com"
IMAP_HOST_OUTLOOK    = "outlook.office365.com"
IMAP_PORT            = 993          # SSL
SMTP_HOST_GMAIL      = "smtp.gmail.com"
SMTP_HOST_OUTLOOK    = "smtp.office365.com"
SMTP_PORT            = 587          # STARTTLS

# Subject keyword used to identify sleeping-cell alert emails
EMAIL_SUBJECT_KEYWORD = os.getenv("EMAIL_SUBJECT_KEYWORD", "sleeping cell")

# How many recent messages to scan when looking for the alert e-mail (Outlook).
EMAIL_MAX_SCAN        = int(os.getenv("EMAIL_MAX_SCAN", "25"))

# ─── Outlook / Microsoft 365 (Graph OAuth) ────────────────────────────────────
# Microsoft killed Basic Auth for IMAP/SMTP on M365, so Outlook uses Graph.
GRAPH_ROOT       = "https://graph.microsoft.com/v1.0"
# App-registration (public client) values used by scripts/get_outlook_token.py
# to mint an access token via device-code sign-in.
MS_CLIENT_ID     = os.getenv("MS_CLIENT_ID", "MS_CLIENT_ID")
# "common" (work + personal), "consumers" (personal @outlook.com/@hotmail only),
# "organizations" (work only), or a tenant GUID (single org).
# IMPORTANT: for a PERSONAL Microsoft account, use "consumers" or "common" —
# a tenant GUID makes the token tenant-scoped and Exchange returns an empty-body
# 401 on /me/messages even though /me works.
MS_TENANT        = os.getenv("MS_TENANT", "common")
# Scopes the Outlook token must carry: Mail.Read (read+attachments), Mail.Send.
# Mail.ReadBasic is intentionally NOT used for fetch because it cannot read
# attachments — the pipeline needs the CSV, so Mail.Read is required.
MS_SCOPES        = ["Mail.Read", "Mail.Send"]

# ─── Unified single sign-in (email -> auto-detected provider -> OAuth) ─────────
# One OAuth consent per provider; the resulting access token is used by
# utils/email_client.py for read + attachment + send.
EMAIL_REDIRECT_URI = os.getenv("EMAIL_REDIRECT_URI", "http://localhost:8501/")

# Google (Gmail API) web-flow credentials + scopes.
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID",     OAUTH_CLIENT_ID)
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", OAUTH_CLIENT_SECRET)
GMAIL_OAUTH_SCOPES   = [
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Microsoft (Graph) scopes for the unified sign-in. List ONLY resource scopes:
# MSAL adds openid/profile/offline_access automatically and RAISES if you pass
# them explicitly ("You cannot use any scope value that is reserved").
# offline_access (hence the refresh token) is therefore already included.
MS_OAUTH_SCOPES      = ["User.Read", "Mail.Read", "Mail.Send"]
# Optional confidential-client secret (leave blank to use a public client).
MS_CLIENT_SECRET     = os.getenv("MS_CLIENT_SECRET", "")

# Print raw HTTP status/headers/body for each mail API call when troubleshooting.
EMAIL_DEBUG          = os.getenv("EMAIL_DEBUG", "0") == "1"


def credentials_status() -> dict:
    """Quick sanity check that real OAuth credentials are configured (not the
    placeholder defaults). Useful to surface misconfiguration early."""
    placeholders = {"CLIENT_ID", "CLIENT_SECRET", "MS_CLIENT_ID", "", None}
    return {
        "google_ok": GOOGLE_CLIENT_ID not in placeholders and GOOGLE_CLIENT_SECRET not in placeholders,
        "microsoft_ok": MS_CLIENT_ID not in placeholders,
    }

# ─── NMS / Operator API ───────────────────────────────────────────────────────
# Set NMS_MOCK=1 to run with synthetic data (no real NMS required)
NMS_MOCK        = os.getenv("NMS_MOCK", "1") == "1"
NMS_BASE_URL    = os.getenv("NMS_BASE_URL",    "https://nms.operator.com/api/v1")
NMS_API_KEY     = os.getenv("NMS_API_KEY",     "YOUR_NMS_API_KEY")
NMS_TIMEOUT     = int(os.getenv("NMS_TIMEOUT", "15"))     # seconds
OBS_DAYS        = int(os.getenv("OBS_DAYS",    "7"))       # observation window

# ─── Model ────────────────────────────────────────────────────────────────────
# "resnet18" | "resnet50"
MODEL_ARCH         = os.getenv("MODEL_ARCH",    "resnet18")
MODEL_WEIGHTS_PATH = os.getenv("MODEL_WEIGHTS", "models/weights/sleeping_cell_model.pt")
# If no weights file exists, the model runs in MOCK mode (random logits)
MODEL_MOCK         = os.getenv("MODEL_MOCK", "1") == "1"

# Classification threshold (sigmoid output ≥ this → sleeping)
DECISION_THRESHOLD = float(os.getenv("DECISION_THRESHOLD", "0.5"))

# ─── Reporting ────────────────────────────────────────────────────────────────
REPORT_RECIPIENT    = os.getenv("REPORT_RECIPIENT", "noc-team@telecom.ng")
REPORT_SUBJECT      = "[SleepGuard] Confirmed Sleeping Cells — {date}"
REPORT_SENDER_NAME  = "SleepGuard Bot"

# ─── Plot ─────────────────────────────────────────────────────────────────────
PLOT_DPI    = 120
PLOT_W_IN   = 8
PLOT_H_IN   = 3.5