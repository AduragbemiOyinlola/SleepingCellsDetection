"""
utils/email_client.py — unified OAuth mail client (all calls via `requests`)
============================================================================
Read + CSV download + send, driven by one OAuth access token per provider.

    Gmail            -> Gmail REST API   (gmail.readonly + gmail.send)
    Outlook / M365   -> Microsoft Graph  (Mail.Read + Mail.Send)

Both providers now use the `requests` library directly. We deliberately do NOT
use google-api-python-client for the data calls: it relies on httplib2, which
fails ("Unable to find the server at gmail.googleapis.com") in environments
with proxy/DNS setups that `requests` handles fine — the same `requests` that
already works for sign-in and for Graph.

Token freshness: sso.py registers a refresh hook via set_token_refresher();
on a 401 we fetch a fresh token and retry once. Provider error bodies AND the
WWW-Authenticate header are surfaced so the real cause is visible.

Public signatures are unchanged; `credential` is the OAuth access token.
"""

from __future__ import annotations

import base64
import binascii
from email.message import EmailMessage
from typing import Optional, Tuple, Callable
from datetime import date, datetime, timezone

import requests

import utils.config as cfg
from utils.config import (
    EMAIL_SUBJECT_KEYWORD, EMAIL_MAX_SCAN, REPORT_SUBJECT, GRAPH_ROOT,
)

GMAIL_ROOT = "https://gmail.googleapis.com/gmail/v1"

# ─── token-refresh hook (registered by utils/sso.py) ──────────────────────────
_token_refresher: Optional[Callable[[str], Optional[str]]] = None
# provider bound to the token at login (set by sso); overrides cfg fallback so
# routing can never drift from the account the user actually signed in with.
_active_provider: Optional[str] = None


def set_token_refresher(fn: Callable[[str], Optional[str]]) -> None:
    global _token_refresher
    _token_refresher = fn


def set_active_provider(provider: Optional[str]) -> None:
    global _active_provider
    _active_provider = (provider or None)


def _refresh(provider: str) -> Optional[str]:
    if _token_refresher is None:
        return None
    try:
        return _token_refresher(provider)
    except Exception:  # noqa: BLE001
        return None


# ─── routing ──────────────────────────────────────────────────────────────────

def _provider() -> str:
    p = _active_provider or getattr(cfg, "EMAIL_PROVIDER", "gmail") or "gmail"
    return p.lower()


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


def _http_error(resp) -> str:
    """Report the real reason: JSON message, then WWW-Authenticate, then body."""
    # 1) JSON error object (Graph: {"error":{"code","message"}};
    #    Google: {"error":{"message"}} or {"error":"...","error_description":"..."})
    try:
        j = resp.json()
        err = j.get("error", j) if isinstance(j, dict) else j
        if isinstance(err, dict):
            msg = (err.get("message") or err.get("error_description") or "").strip()
            code = err.get("code") or err.get("status")
            detail = f"{code}: {msg}" if (code and msg) else (msg or str(code or "")).strip()
        else:
            detail = str(err).strip()
        if detail:
            return f"HTTP {resp.status_code} — {detail}"
    except Exception:  # noqa: BLE001
        pass
    # 2) WWW-Authenticate header (Graph often puts the reason here)
    www = resp.headers.get("WWW-Authenticate", "")
    if "error_description" in www:
        return f"HTTP {resp.status_code} — {www.split('error_description=')[-1].strip().strip(chr(34))[:200]}"
    # 3) raw body snippet (reveals proxy/HTML interception)
    body = (resp.text or "").strip().replace("\n", " ")
    return f"HTTP {resp.status_code}" + (f" — {body[:200]}" if body else " (empty response body)")


def _request(method: str, url: str, token: str, provider: str, *,
             params: dict | None = None, json_body: dict | None = None,
             _retried: bool = False):
    """HTTP call with one automatic token-refresh retry on 401."""
    resp = requests.request(
        method, url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params, json=json_body, timeout=30,
    )
    if resp.status_code == 401 and not _retried:
        fresh = _refresh(provider)
        if fresh and fresh != token:
            return _request(method, url, fresh, provider, params=params,
                            json_body=json_body, _retried=True)
    return resp


# =============================================================================
# Microsoft Graph (Outlook / M365)
# =============================================================================

def _graph_connect(token: str) -> Tuple[bool, str]:
    resp = _request("GET", f"{GRAPH_ROOT}/me", token, "outlook",
                    params={"$select": "mail,userPrincipalName,displayName"})
    if resp.status_code == 200:
        me = resp.json()
        return True, f"Connected to Microsoft 365 mailbox: {me.get('mail') or me.get('userPrincipalName','')}."
    return False, f"Graph connection failed — {_http_error(resp)}"


def _graph_fetch(token: str, keyword: str) -> Tuple[Optional[dict], str]:
    try:
        resp = _request("GET", f"{GRAPH_ROOT}/me/messages", token, "outlook",
                        params={"$search": f'"subject:{keyword}"',
                                "$select": "id,subject,from,receivedDateTime,hasAttachments",
                                "$top": EMAIL_MAX_SCAN})
        if resp.status_code != 200:
            return None, f"Error fetching email — {_http_error(resp)}"

        items = [it for it in resp.json().get("value", [])
                 if keyword.lower() in (it.get("subject") or "").lower()]
        if not items:
            return None, f"No emails found with subject containing '{keyword}'."

        def _recv(it):
            v = it.get("receivedDateTime")
            return (datetime.fromisoformat(v.replace("Z", "+00:00"))
                    if v else datetime.min.replace(tzinfo=timezone.utc))
        items.sort(key=_recv, reverse=True)
        msg = items[0]
        frm = (msg.get("from") or {}).get("emailAddress") or {}
        result = {"subject": msg.get("subject", ""),
                  "sender": f'{frm.get("name","")} <{frm.get("address","")}>'.strip(),
                  "date": msg.get("receivedDateTime", ""), "body": "",
                  "csv_bytes": None, "csv_name": None}

        ar = _request("GET", f"{GRAPH_ROOT}/me/messages/{msg['id']}/attachments", token, "outlook")
        if ar.status_code == 200:
            for att in ar.json().get("value", []):
                name = att.get("name", "") or ""
                if (att.get("@odata.type", "").endswith("fileAttachment")
                        and name.lower().endswith(".csv") and result["csv_bytes"] is None):
                    content = att.get("contentBytes")
                    if content:
                        try:
                            result["csv_bytes"] = base64.b64decode(content)
                            result["csv_name"] = name
                        except (binascii.Error, ValueError):
                            pass
        return result, f"Email retrieved: '{result['subject']}' from {result['sender']}."
    except Exception as e:  # noqa: BLE001
        return None, f"Error fetching email: {e}"


def _graph_send(token, recipient, subject, body, csv_bytes, csv_filename) -> Tuple[bool, str]:
    payload = {"message": {
        "subject": subject, "body": {"contentType": "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": recipient}}],
        "attachments": [{"@odata.type": "#microsoft.graph.fileAttachment",
                         "name": csv_filename, "contentType": "text/csv",
                         "contentBytes": base64.b64encode(csv_bytes).decode()}],
    }, "saveToSentItems": True}
    try:
        resp = _request("POST", f"{GRAPH_ROOT}/me/sendMail", token, "outlook", json_body=payload)
        if resp.status_code in (200, 202):
            return True, f"Report sent to {recipient} via Microsoft Graph."
        return False, f"Failed to send report — {_http_error(resp)}"
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to send email: {e}"


# =============================================================================
# Gmail (Gmail REST API via requests — no httplib2)
# =============================================================================

def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _gmail_walk(payload: dict):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _gmail_walk(part)


def _gmail_connect(token: str) -> Tuple[bool, str]:
    resp = _request("GET", f"{GMAIL_ROOT}/users/me/profile", token, "gmail")
    if resp.status_code == 200:
        return True, f"Connected to Gmail mailbox: {resp.json().get('emailAddress','')}."
    return False, f"Gmail connection failed — {_http_error(resp)}"


def _gmail_fetch(token: str, keyword: str) -> Tuple[Optional[dict], str]:
    try:
        lst = _request("GET", f"{GMAIL_ROOT}/users/me/messages", token, "gmail",
                       params={"q": f'subject:"{keyword}" in:inbox', "maxResults": EMAIL_MAX_SCAN})
        if lst.status_code != 200:
            return None, f"Error fetching email — {_http_error(lst)}"
        ids = [m["id"] for m in lst.json().get("messages", [])]
        if not ids:
            return None, f"No emails found with subject containing '{keyword}'."

        gm = _request("GET", f"{GMAIL_ROOT}/users/me/messages/{ids[0]}", token, "gmail",
                      params={"format": "full"})
        if gm.status_code != 200:
            return None, f"Error fetching email — {_http_error(gm)}"
        full = gm.json()
        headers = {h["name"].lower(): h["value"]
                   for h in full.get("payload", {}).get("headers", [])}
        result = {"subject": headers.get("subject", ""), "sender": headers.get("from", ""),
                  "date": headers.get("date", ""), "body": "",
                  "csv_bytes": None, "csv_name": None}
        for part in _gmail_walk(full.get("payload", {})):
            fname = (part.get("filename") or "")
            bd = part.get("body", {})
            if fname.lower().endswith(".csv") and result["csv_bytes"] is None:
                data = bd.get("data")
                if data is None and bd.get("attachmentId"):
                    at = _request("GET",
                                  f"{GMAIL_ROOT}/users/me/messages/{ids[0]}/attachments/{bd['attachmentId']}",
                                  token, "gmail")
                    if at.status_code == 200:
                        data = at.json().get("data")
                if data:
                    result["csv_bytes"] = _b64url_decode(data)
                    result["csv_name"] = fname
            if part.get("mimeType") == "text/plain" and not result["body"] and bd.get("data"):
                result["body"] = _b64url_decode(bd["data"]).decode("utf-8", "replace")
        return result, f"Email retrieved: '{result['subject']}' from {result['sender']}."
    except Exception as e:  # noqa: BLE001
        return None, f"Error fetching email: {e}"


def _gmail_send(token, recipient, subject, body, csv_bytes, csv_filename) -> Tuple[bool, str]:
    try:
        em = EmailMessage()
        em["To"] = recipient
        em["Subject"] = subject
        em.set_content(body)
        em.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=csv_filename)
        raw = base64.urlsafe_b64encode(em.as_bytes()).decode()
        resp = _request("POST", f"{GMAIL_ROOT}/users/me/messages/send", token, "gmail",
                        json_body={"raw": raw})
        if resp.status_code in (200, 202):
            return True, f"Report sent to {recipient} via Gmail."
        return False, f"Failed to send report — {_http_error(resp)}"
    except Exception as e:  # noqa: BLE001
        return False, f"Failed to send email: {e}"


# =============================================================================
# Public API
# =============================================================================

def connect_imap(email_address: str, credential: str) -> Tuple[bool, str]:
    if not credential:
        return False, "No access token available — please sign in again."
    return _graph_connect(credential) if _is_outlook() else _gmail_connect(credential)


def fetch_sleeping_cell_email(email_address: str, credential: str,
                              keyword: str = EMAIL_SUBJECT_KEYWORD
                              ) -> Tuple[Optional[dict], str]:
    if not credential:
        return None, "No access token available — please sign in again."
    return (_graph_fetch(credential, keyword) if _is_outlook()
            else _gmail_fetch(credential, keyword))


def send_report_email(sender_address: str, sender_password: str, recipient: str,
                      csv_bytes: bytes, csv_filename: str = "sleeping_cells_report.csv",
                      extra_body: str = "") -> Tuple[bool, str]:
    if not sender_password:
        return False, "No access token available — please sign in again."
    subject = REPORT_SUBJECT.format(date=date.today().isoformat())
    body = _report_body(extra_body)
    token = sender_password
    return (_graph_send(token, recipient, subject, body, csv_bytes, csv_filename)
            if _is_outlook()
            else _gmail_send(token, recipient, subject, body, csv_bytes, csv_filename))