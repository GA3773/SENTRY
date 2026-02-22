"""
Lenz API authentication via ADFS form-based OAuth2 flow.

Flow:
1. GET Lenz → 302 to ADFS /authorize
2. GET ADFS → returns HTML login form
3. POST credentials to ADFS form action
4. ADFS validates → 302 chain back to Lenz
5. Lenz sets session cookies
"""

import logging
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_session: requests.Session | None = None


def _authenticate_adfs() -> requests.Session:
    """Authenticate to Lenz via ADFS form-based OAuth2 flow."""
    username = os.getenv("LENZ_USERNAME")
    password = os.getenv("LENZ_PASSWORD")
    base_url = os.getenv("LENZ_API_BASE_URL")

    if not username or not password:
        raise ValueError("LENZ_USERNAME and LENZ_PASSWORD must be set in .env")

    session = requests.Session()
    session.verify = True

    # Step 1: Hit Lenz — will redirect to ADFS
    logger.info("Step 1: Hitting Lenz API to get ADFS redirect...")
    resp = session.get(
        f"{base_url}/def",
        params={"name": "TB-Derivatives"},
        allow_redirects=True,
        timeout=30,
    )

    if resp.status_code != 200:
        raise ConnectionError(
            f"Expected ADFS login page, got status {resp.status_code}"
        )

    html = resp.text
    logger.info("Step 1 complete. Final URL: %s", resp.url)

    # Step 2: Parse the login form
    form_action_match = re.search(
        r'<form[^>]*action=["\']([^"\']+)["\']', html, re.IGNORECASE
    )
    if not form_action_match:
        raise ConnectionError(
            f"Could not find login form in ADFS page. HTML preview: {html[:500]}"
        )

    form_action = form_action_match.group(1)
    if form_action.startswith("/"):
        from urllib.parse import urlparse

        parsed = urlparse(str(resp.url))
        form_action = f"{parsed.scheme}://{parsed.netloc}{form_action}"

    logger.info("Step 2: Found form action: %s", form_action)

    # Extract all hidden input fields
    hidden_fields: dict[str, str] = {}
    for match in re.finditer(
        r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\']'
        r'[^>]*value=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    ):
        hidden_fields[match.group(1)] = match.group(2)

    # Also try reversed attribute order (value before name)
    for match in re.finditer(
        r'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']'
        r'[^>]*type=["\']hidden["\']',
        html,
        re.IGNORECASE,
    ):
        hidden_fields[match.group(2)] = match.group(1)

    logger.info(
        "Step 2: Found %d hidden fields: %s",
        len(hidden_fields),
        list(hidden_fields.keys()),
    )

    # Step 3: POST credentials
    # If username doesn't have domain, add NAEAST
    if "\\" not in username and "@" not in username:
        form_username = f"NAEAST\\{username}"
    else:
        form_username = username

    form_data = {
        **hidden_fields,
        "UserName": form_username,
        "Password": password,
        "AuthMethod": "FormsAuthentication",
    }

    logger.info("Step 3: POSTing credentials to %s", form_action)
    resp2 = session.post(
        form_action,
        data=form_data,
        allow_redirects=True,
        timeout=30,
    )

    logger.info(
        "Step 3 complete. Status: %s, URL: %s, Content-Type: %s",
        resp2.status_code,
        resp2.url,
        resp2.headers.get("content-type", ""),
    )

    # Check if we ended up back at Lenz with JSON
    content_type = resp2.headers.get("content-type", "")
    if "json" in content_type:
        logger.info("ADFS authentication successful — got JSON response")
        return session

    # Maybe we need one more request with the session cookies
    if "lenz-app" in str(resp2.url):
        resp3 = session.get(
            f"{base_url}/def",
            params={"name": "TB-Derivatives"},
            allow_redirects=True,
            timeout=30,
        )
        if "json" in resp3.headers.get("content-type", ""):
            logger.info("ADFS auth successful on retry")
            return session

    raise ConnectionError(
        f"ADFS form auth failed.\n"
        f"Final URL: {resp2.url}\n"
        f"Status: {resp2.status_code}\n"
        f"Content-Type: {content_type}\n"
        f"Body preview: {resp2.text[:500]}"
    )


def get_authenticated_session() -> requests.Session:
    """Get cached session or create new one."""
    global _session
    if _session is not None:
        try:
            test = _session.get(
                f"{os.getenv('LENZ_API_BASE_URL')}/def",
                params={"name": "TB-Derivatives"},
                timeout=15,
                allow_redirects=False,
            )
            if test.status_code == 200 and "json" in test.headers.get(
                "content-type", ""
            ):
                return _session
        except Exception:
            pass
        _session = None

    _session = _authenticate_adfs()
    return _session


def invalidate_session() -> None:
    """Force re-auth on next call."""
    global _session
    _session = None


def lenz_fetch(essential_name: str) -> dict:
    """Fetch essential definition from Lenz with auto-auth."""
    session = get_authenticated_session()
    response = session.get(
        f"{os.getenv('LENZ_API_BASE_URL')}/def",
        params={"name": essential_name},
        timeout=30,
        allow_redirects=True,
    )

    # Session expired? Re-auth and retry
    if "json" not in response.headers.get("content-type", ""):
        invalidate_session()
        session = get_authenticated_session()
        response = session.get(
            f"{os.getenv('LENZ_API_BASE_URL')}/def",
            params={"name": essential_name},
            timeout=30,
            allow_redirects=True,
        )

    response.raise_for_status()
    return response.json()
