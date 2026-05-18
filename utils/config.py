"""
utils/config.py — Central configuration
========================================
Prefer environment variables for secrets in production.
Fallback defaults are provided for local/demo usage.
"""

import os

# ─── Auth ─────────────────────────────────────────────────────────────────────
# "DEMO" | "OAUTH"
AUTH_MODE = os.getenv("AUTH_MODE", "DEMO")

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
OAUTH_CLIENT_ID     = os.getenv("OAUTH_CLIENT_ID",     "YOUR_CLIENT_ID_HERE")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
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