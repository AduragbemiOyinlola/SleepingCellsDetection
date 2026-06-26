#!/usr/bin/env python3
"""
scripts/get_outlook_token.py — mint a Microsoft Graph token for Outlook/M365
=============================================================================
Microsoft 365 no longer allows IMAP/SMTP password login, so the Outlook path in
SleepGuard authenticates to Microsoft Graph with an OAuth access token. This
helper signs you in via the device-code flow (no web server, no client secret)
and prints an access token you paste into the dashboard's Step 1 password box
(the field labelled "App Password / OAuth Token").

Setup (one-time):
  1. Azure Portal -> App registrations -> New registration
       - Supported account types: match your users (e.g. "any org + personal")
       - Authentication -> Advanced -> "Allow public client flows" = YES
  2. API permissions -> Microsoft Graph -> Delegated:
       - Mail.Read     (read mailbox + attachments — needed for the CSV)
       - Mail.Send     (send the report)
     then Grant admin consent if your tenant requires it.
  3. Copy the Application (client) ID and your tenant, then export:
       export MS_CLIENT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
       export MS_TENANT="common"      # or your tenant GUID

Run:
       python scripts/get_outlook_token.py

It prints a URL + code; sign in, approve, and the access token is shown.
Access tokens last ~60-90 min — mint a fresh one per pipeline run, or extend
this script to cache the refresh token if you need longer-lived access.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import msal
from utils.config import MS_CLIENT_ID, MS_TENANT, MS_SCOPES


def main():
    if MS_CLIENT_ID in ("", "MS_CLIENT_ID"):
        print("ERROR: set MS_CLIENT_ID (and MS_TENANT) first. See the docstring.")
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{MS_TENANT}"
    app = msal.PublicClientApplication(MS_CLIENT_ID, authority=authority)

    flow = app.initiate_device_flow(scopes=MS_SCOPES)
    if "user_code" not in flow:
        print("Failed to start device flow:", flow)
        sys.exit(1)

    print("\n" + flow["message"] + "\n")        # "go to microsoft.com/devicelogin, enter ABC-DEF"
    result = app.acquire_token_by_device_flow(flow)   # blocks until you finish sign-in

    if "access_token" not in result:
        print("Sign-in failed:", result.get("error_description", result))
        sys.exit(1)

    print("=" * 70)
    print("Granted scopes :", result.get("scope", ""))
    print("Expires in     :", result.get("expires_in", "?"), "seconds")
    print("=" * 70)
    print("\nACCESS TOKEN (paste into dashboard Step 1 password box):\n")
    print(result["access_token"])
    print()


if __name__ == "__main__":
    main()