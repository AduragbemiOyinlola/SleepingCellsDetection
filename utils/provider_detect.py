"""
utils/provider_detect.py — detect a mailbox's provider from the e-mail address
==============================================================================
Powers the unified "enter your e-mail and we figure out the rest" sign-in.

Given an address it returns one of:  "gmail" | "outlook" | "unknown"
(plus a short human-readable reason), using a layered strategy:

  1. Known consumer domains      — instant, offline   (gmail.com, outlook.com, …)
  2. MX-record lookup            — works for ANY custom domain (Workspace / M365)
                                   Google  -> hosts under google.com / googlemail.com
                                   Microsoft -> *.mail.protection.outlook.com
  3. Microsoft tenant probe      — no-dependency backstop via the per-domain
                                   OpenID-Connect metadata endpoint.

Step 2 needs `dnspython` (pip install dnspython). If it isn't installed the
detector still resolves consumer domains and Microsoft tenants (step 3); only
Google Workspace *custom* domains then fall through to "unknown".
"""

from __future__ import annotations

from typing import Tuple

import requests

# ─── Known consumer domains (fast path, no network) ───────────────────────────

GOOGLE_CONSUMER = {
    "gmail.com", "googlemail.com",
}

MICROSOFT_CONSUMER = {
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "passport.com", "windowslive.com", "hotmail.co.uk", "live.co.uk",
    "outlook.co.uk", "hotmail.fr", "live.fr", "outlook.fr",
}

# ─── MX host suffixes that identify each provider ─────────────────────────────

GOOGLE_MX_SUFFIXES = ("google.com", "googlemail.com")          # aspmx.l.google.com
MICROSOFT_MX_SUFFIXES = ("outlook.com", "mail.protection.outlook.com",
                         "protection.outlook.com", "office365.us")


def _domain_of(email: str) -> str:
    return email.split("@")[-1].strip().lower().rstrip(".")


def _mx_hosts(domain: str, timeout: float = 5.0) -> list[str]:
    """Return the list of MX exchange hostnames for *domain* (lower-cased)."""
    try:
        import dns.resolver  # optional dependency
    except ImportError:
        return []
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        return [str(r.exchange).rstrip(".").lower() for r in answers]
    except Exception:  # noqa: BLE001  — NXDOMAIN, no MX, timeout, etc.
        return []


def _classify_mx(hosts: list[str]) -> str | None:
    for h in hosts:
        if any(h == s or h.endswith("." + s) for s in GOOGLE_MX_SUFFIXES):
            return "gmail"
    for h in hosts:
        if any(h == s or h.endswith("." + s) for s in MICROSOFT_MX_SUFFIXES):
            return "outlook"
    return None


def _is_microsoft_tenant(domain: str, timeout: float = 5.0) -> bool:
    """
    No-dependency Microsoft backstop: the per-domain OIDC metadata endpoint
    returns 200 for a managed/federated Microsoft tenant, 400 otherwise.
    """
    url = f"https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration"
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def detect_provider(email: str, use_network: bool = True) -> Tuple[str, str]:
    """
    Detect the mail provider for *email*.

    Returns (provider, reason) where provider is "gmail" | "outlook" | "unknown".
    Set use_network=False to restrict detection to the offline consumer tables.
    """
    if not email or "@" not in email:
        return "unknown", "not a valid e-mail address"

    domain = _domain_of(email)

    # 1) consumer fast path
    if domain in GOOGLE_CONSUMER:
        return "gmail", "known Google consumer domain"
    if domain in MICROSOFT_CONSUMER:
        return "outlook", "known Microsoft consumer domain"

    if not use_network:
        return "unknown", "custom domain — enable network detection to resolve"

    # 2) MX lookup (handles Workspace + M365 custom domains)
    hosts = _mx_hosts(domain)
    mx_verdict = _classify_mx(hosts)
    if mx_verdict == "gmail":
        return "gmail", f"MX points to Google Workspace ({hosts[0]})"
    if mx_verdict == "outlook":
        return "outlook", f"MX points to Microsoft 365 ({hosts[0]})"

    # 3) Microsoft tenant backstop (covers M365 domains whose MX is a 3rd-party
    #    spam filter, e.g. Proofpoint/Mimecast, so the MX suffix isn't Microsoft)
    if _is_microsoft_tenant(domain):
        return "outlook", "domain is a registered Microsoft 365 tenant"

    return "unknown", f"could not determine provider for '{domain}'"