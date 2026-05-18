"""
utils/email_client.py — IMAP fetch + SMTP send
===============================================
Connects to Gmail or Outlook via IMAP/SSL to read emails,
and sends reports via SMTP/STARTTLS.

Usage
-----
    from utils.email_client import connect_imap, fetch_sleeping_cell_email, send_report_email

Security notes
--------------
- For Gmail:   enable IMAP in settings; use an App Password (not your main password)
  if 2FA is on. Store credentials in env vars / st.secrets, never hardcoded.
- For Outlook: use OAuth tokens for M365 in production (basic auth deprecated).
"""

import imaplib
import smtplib
import email as email_lib
import io
from email import policy
from email.message import EmailMessage
from typing import Optional, Tuple
from datetime import date

from utils.config import (
    EMAIL_PROVIDER,
    IMAP_HOST_GMAIL,
    IMAP_HOST_OUTLOOK,
    IMAP_PORT,
    SMTP_HOST_GMAIL,
    SMTP_HOST_OUTLOOK,
    SMTP_PORT,
    EMAIL_SUBJECT_KEYWORD,
    REPORT_SUBJECT,
    REPORT_SENDER_NAME,
)


def _imap_host() -> str:
    return IMAP_HOST_GMAIL if EMAIL_PROVIDER == "gmail" else IMAP_HOST_OUTLOOK


def _smtp_host() -> str:
    return SMTP_HOST_GMAIL if EMAIL_PROVIDER == "gmail" else SMTP_HOST_OUTLOOK


# ─── Connection ───────────────────────────────────────────────────────────────

def connect_imap(email_address: str, password: str) -> Tuple[bool, str]:
    """
    Attempt to open an authenticated IMAP connection.
    Returns (success: bool, message: str).
    """
    try:
        mail = imaplib.IMAP4_SSL(_imap_host(), IMAP_PORT)
        mail.login(email_address, password)
        mail.logout()
        return True, "Connected successfully."
    except imaplib.IMAP4.error as e:
        return False, f"Authentication failed: {e}"
    except Exception as e:
        return False, f"Connection error: {e}"


# ─── Fetch ────────────────────────────────────────────────────────────────────

def fetch_sleeping_cell_email(
    email_address: str,
    password: str,
    keyword: str = EMAIL_SUBJECT_KEYWORD,
) -> Tuple[Optional[dict], str]:
    """
    Search INBOX for the most recent email whose subject contains *keyword*.
    Returns (email_dict, log_message).

    email_dict keys:
        subject   str
        sender    str
        date      str
        body      str
        csv_bytes bytes | None   — first .csv attachment found, or None
        csv_name  str  | None
    """
    try:
        mail = imaplib.IMAP4_SSL(_imap_host(), IMAP_PORT)
        mail.login(email_address, password)
        mail.select("INBOX")

        # Search — IMAP SUBJECT search is case-insensitive on most servers
        _, data = mail.search(None, f'SUBJECT "{keyword}"')
        ids = data[0].split()

        if not ids:
            mail.logout()
            return None, f"No emails found with subject containing '{keyword}'."

        # Most recent = last ID
        latest_id = ids[-1]
        _, msg_data = mail.fetch(latest_id, "(RFC822)")
        raw = msg_data[0][1]
        mail.logout()

        msg = email_lib.message_from_bytes(raw, policy=policy.default)

        result = {
            "subject":   msg.get("Subject", ""),
            "sender":    msg.get("From", ""),
            "date":      msg.get("Date", ""),
            "body":      "",
            "csv_bytes": None,
            "csv_name":  None,
        }

        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get_content_disposition() or ""

            if ct == "text/plain" and "attachment" not in cd:
                result["body"] = part.get_payload(decode=True).decode("utf-8", errors="replace")

            if "attachment" in cd or ct in ("text/csv", "application/csv",
                                            "application/octet-stream",
                                            "application/vnd.ms-excel"):
                fname = part.get_filename() or ""
                if fname.lower().endswith(".csv"):
                    result["csv_bytes"] = part.get_payload(decode=True)
                    result["csv_name"]  = fname

        return result, f"Email retrieved: '{result['subject']}' from {result['sender']}."

    except Exception as e:
        return None, f"Error fetching email: {e}"


# ─── Send ─────────────────────────────────────────────────────────────────────

def send_report_email(
    sender_address: str,
    sender_password: str,
    recipient: str,
    csv_bytes: bytes,
    csv_filename: str = "sleeping_cells_report.csv",
    extra_body: str = "",
) -> Tuple[bool, str]:
    """
    Send the confirmed sleeping cells CSV report via SMTP.
    Returns (success: bool, message: str).
    """
    try:
        subject = REPORT_SUBJECT.format(date=date.today().isoformat())

        msg = EmailMessage()
        msg["From"]    = f"{REPORT_SENDER_NAME} <{sender_address}>"
        msg["To"]      = recipient
        msg["Subject"] = subject
        msg.set_content(
            f"Hello,\n\n"
            f"The automated SleepGuard pipeline has completed its analysis.\n"
            f"Please find the confirmed sleeping cells report attached.\n\n"
            f"{extra_body}\n\n"
            f"-- SleepGuard Automated System"
        )
        msg.add_attachment(
            csv_bytes,
            maintype="text",
            subtype="csv",
            filename=csv_filename,
        )

        with smtplib.SMTP(_smtp_host(), SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(sender_address, sender_password)
            server.send_message(msg)

        return True, f"Report sent to {recipient}."
    except Exception as e:
        return False, f"Failed to send email: {e}"