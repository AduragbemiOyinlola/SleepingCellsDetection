"""
utils/email_client.py — unified OAuth mail client (Gmail API + Microsoft Graph)
===============================================================================
One access token drives everything, for whichever provider the user signed in
with. This is what makes the single sign-in possible: the user authenticates
once via OAuth, and the same token is used to read the alert e-mail, download
its CSV attachment, and send the report back.

    Gmail            -> Gmail API   (gmail.readonly + gmail.send)
    Outlook / M365   -> Microsoft Graph (Mail.Read + Mail.Send)

Public functions keep the SAME names/signatures the dashboard already calls, so
this stays a drop-in. The `credential` argument is the OAuth ACCESS TOKEN
(obtained by the unified sign-in in utils/auth.py); the e-mail address is only
used for display. The active provider is read live from utils.config.EMAIL_PROVIDER.

    connect_imap(email, token)                 -> (ok, msg)
    fetch_sleeping_cell_email(email, token, …) -> (email_dict | None, msg)
    send_report_email(email, token, recipient,…) -> (ok, msg)
"""

from __future__ import annotations

import base64
import binascii
from email.message import EmailMessage
from typing import Optional, Tuple
from datetime import date, datetime, timezone

import requests

import utils.config as cfg
from utils.config import (
    EMAIL_SUBJECT_KEYWORD,
    EMAIL_MAX_SCAN,
    REPORT_SUBJECT,
    REPORT_SENDER_NAME,
    GRAPH_ROOT,
)


# -----------------------------------------------------------------------------
# Provider routing  (read live so the sign-in's provider choice is honoured)
# -----------------------------------------------------------------------------

def _provider() -> str:
    return (getattr(cfg, "EMAIL_PROVIDER", "gmail") or "gmail").lower()


def _is_outlook() -> bool:
    return _provider() in ("outlook", "microsoft", "m365")


def _report_body(extra_body: str) -> str:
    return (
        "Hello,\n\n"
        "The automated SleepGuard pipeline has completed its analysis.\n"
        "Please find the confirmed sleeping cells report attached.\n\n"
        f"{extra_body}\n\n"
        "-- SleepGuard Automated System"
    )


# =============================================================================
# Gmail (Gmail API, OAuth token)
# =============================================================================

def _gmail_service(token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(token=token)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _gmail_connect(token: str) -> Tuple[bool, str]:
    try:
        svc = _gmail_service(token)
        prof = svc.users().getProfile(userId="me").execute()
        return True, f"Connected to Gmail mailbox: {prof.get('emailAddress','')}."
    except Exception as e:  # noqa: BLE001
        return False, f"Gmail connection failed: {e}"


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _gmail_walk(payload: dict):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _gmail_walk(part)


def _gmail_fetch(token: str, keyword: str) -> Tuple[Optional[dict], str]:
    try:
        svc = _gmail_service(token)
        resp = svc.users().messages().list(
            userId="me", q=f'subject:"{keyword}" in:inbox', maxResults=EMAIL_MAX_SCAN,
        ).execute()
        ids = [m["id"] for m in resp.get("messages", [])]
        if not ids:
            return None, f"No emails found with subject containing '{keyword}'."

        # q returns newest-first; take the first message.
        full = svc.users().messages().get(userId="me", id=ids[0], format="full").execute()
        headers = {h["name"].lower(): h["value"]
                   for h in full.get("payload", {}).get("headers", [])}
        result = {
            "subject":   headers.get("subject", ""),
            "sender":    headers.get("from", ""),
            "date":      headers.get("date", ""),
            "body":      "",
            "csv_bytes": None,
            "csv_name":  None,
        }
        for part in _gmail_walk(full.get("payload", {})):
            fname = (part.get("filename") or "")
            body = part.get("body", {})
            if fname.lower().endswith(".csv") and result["csv_bytes"] is None:
                data = body.get("data")
                if data is None and body.get("attachmentId"):
                    att = svc.users().messages().attachments().get(
                        userId="me", messageId=ids[0], id=body["attachmentId"],
                    ).execute()
                    data = att.get("data")
                if data:
                    result["csv_bytes"] = _b64url_decode(data)
                    result["csv_name"] = fname
            if part.get("mimeType") == "text/plain" and not result["body"] and body.get("data"):
                result["body"] = _b64url_decode(body["data"]).decode("utf-8", "replace")

        return result, f"Email retrieved: '{result['subject']}' from {result['sender']}."
    except Exception as e:  # noqa: BLE001
        return None, f"Error fetching email: {e}"


def _gmail_send(token: str, recipient: str, subject: str, body: str,
                csv_bytes: bytes, csv_filename: str) -> Tuple[bool, str]:
    try:
        svc = _gmail_service(token)
        em = EmailMessage()
        em["To"] = recipient
        em["Subject"] = subject
        em.set_content(body)
        em.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=csv_filename)
        raw = base64.urlsafe_b64encode(em.as_bytes()).decode()
        svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True, f"Report sent to {recipient} via Gmail."
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to send email: {e}"


# =============================================================================
# Outlook / M365 (Microsoft Graph, OAuth token)
# =============================================================================

def _graph_get(token: str, path: str, params: dict | None = None):
    r = requests.get(
        f"{GRAPH_ROOT}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _graph_connect(token: str) -> Tuple[bool, str]:
    try:
        me = _graph_get(token, "/me", {"$select": "mail,userPrincipalName,displayName"})
        who = me.get("mail") or me.get("userPrincipalName", "")
        return True, f"Connected to Microsoft 365 mailbox: {who}."
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 401:
            return False, "Authentication failed: Graph token invalid or expired."
        return False, f"Graph connection failed (HTTP {code})."
    except Exception as e:  # noqa: BLE001
        return False, f"Connection error: {e}"


def _graph_fetch(token: str, keyword: str) -> Tuple[Optional[dict], str]:
    try:
        select = "id,subject,from,receivedDateTime,hasAttachments"
        data = _graph_get(
            token, "/me/messages",
            {"$search": f'"subject:{keyword}"', "$select": select, "$top": EMAIL_MAX_SCAN},
        )
        items = [it for it in data.get("value", [])
                 if keyword.lower() in (it.get("subject") or "").lower()]
        if not items:
            return None, f"No emails found with subject containing '{keyword}'."

        def _received(it):
            v = it.get("receivedDateTime")
            return (datetime.fromisoformat(v.replace("Z", "+00:00"))
                    if v else datetime.min.replace(tzinfo=timezone.utc))
        items.sort(key=_received, reverse=True)
        msg = items[0]

        frm = (msg.get("from") or {}).get("emailAddress") or {}
        sender = f'{frm.get("name","")} <{frm.get("address","")}>'.strip()
        result = {
            "subject":   msg.get("subject", ""),
            "sender":    sender,
            "date":      msg.get("receivedDateTime", ""),
            "body":      "",
            "csv_bytes": None,
            "csv_name":  None,
        }
        atts = _graph_get(token, f"/me/messages/{msg['id']}/attachments").get("value", [])
        for att in atts:
            name = att.get("name", "") or ""
            is_file = att.get("@odata.type", "").endswith("fileAttachment")
            if is_file and name.lower().endswith(".csv") and result["csv_bytes"] is None:
                content = att.get("contentBytes")
                if content:
                    try:
                        result["csv_bytes"] = base64.b64decode(content)
                        result["csv_name"] = name
                    except (binascii.Error, ValueError):
                        pass
        return result, f"Email retrieved: '{result['subject']}' from {result['sender']}."
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 403:
            return None, "Graph 403 — token lacks Mail.Read."
        return None, f"Error fetching email (HTTP {code})."
    except Exception as e:  # noqa: BLE001
        return None, f"Error fetching email: {e}"


def _graph_send(token: str, recipient: str, subject: str, body: str,
                csv_bytes: bytes, csv_filename: str) -> Tuple[bool, str]:
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": csv_filename,
                "contentType": "text/csv",
                "contentBytes": base64.b64encode(csv_bytes).decode(),
            }],
        },
        "saveToSentItems": True,
    }
    try:
        r = requests.post(
            f"{GRAPH_ROOT}/me/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
        if r.status_code in (200, 202):
            return True, f"Report sent to {recipient} via Microsoft Graph."
        if r.status_code == 403:
            return False, "Graph 403 — token lacks Mail.Send."
        return False, f"Graph sendMail failed (HTTP {r.status_code}): {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to send email: {e}"


# =============================================================================
# Public API  (drop-in signatures; `credential` is the OAuth access token)
# =============================================================================

def connect_imap(email_address: str, credential: str) -> Tuple[bool, str]:
    """Validate the token against the mailbox. (Name kept for compatibility.)"""
    return _graph_connect(credential) if _is_outlook() else _gmail_connect(credential)


def fetch_sleeping_cell_email(email_address: str, credential: str,
                              keyword: str = EMAIL_SUBJECT_KEYWORD
                              ) -> Tuple[Optional[dict], str]:
    """Find the alert e-mail and download its CSV. Returns (email_dict, log)."""
    return (_graph_fetch(credential, keyword) if _is_outlook()
            else _gmail_fetch(credential, keyword))


def send_report_email(sender_address: str, sender_password: str, recipient: str,
                      csv_bytes: bytes, csv_filename: str = "sleeping_cells_report.csv",
                      extra_body: str = "") -> Tuple[bool, str]:
    """Send the confirmed-cells CSV report. `sender_password` is the access token."""
    subject = REPORT_SUBJECT.format(date=date.today().isoformat())
    body = _report_body(extra_body)
    token = sender_password
    return (_graph_send(token, recipient, subject, body, csv_bytes, csv_filename)
            if _is_outlook()
            else _gmail_send(token, recipient, subject, body, csv_bytes, csv_filename))