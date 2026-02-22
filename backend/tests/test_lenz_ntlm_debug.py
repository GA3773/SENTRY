"""
Debug script to test Lenz API NTLM authentication.

Tries multiple domain prefixes to find which one works with ADFS.

Usage:
    cd backend
    python tests/test_lenz_ntlm_debug.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from requests_ntlm import HttpNtlmAuth
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv("LENZ_API_BASE_URL", "https://lenz-app.prod.aws.jpmchase.net/lenz/essentials")
username = os.getenv("LENZ_USERNAME", "")
password = os.getenv("LENZ_PASSWORD", "")

print(f"Base URL: {base_url}")
print(f"Username: {username}")
print(f"Password length: {len(password)}")
print()

# Domain prefixes to try
domain_prefixes = [
    "",              # no domain
    "AMER\\",        # AMER domain
    "NAM\\",         # NAM domain
    "JPMC\\",        # JPMC domain
]

# SSL verification options
verify_options = [True, False]

for verify in verify_options:
    for prefix in domain_prefixes:
        full_username = f"{prefix}{username}"
        label = f"verify={verify}, user='{full_username}'"
        print(f"--- Trying: {label} ---")

        try:
            auth = HttpNtlmAuth(full_username, password)
            resp = requests.get(
                f"{base_url}/def",
                params={"name": "TB-Derivatives"},
                auth=auth,
                timeout=30,
                verify=verify,
            )
            content_type = resp.headers.get("content-type", "")
            print(f"  Status: {resp.status_code}")
            print(f"  Content-Type: {content_type}")

            if "json" in content_type:
                print(f"  JSON keys: {list(resp.json().keys())}")
                print(f"  SUCCESS — use this config!")
                print()
                sys.exit(0)
            else:
                print(f"  First 500 chars: {resp.text[:500]}")
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

print("All combinations failed. Check credentials and network access (JPMC VPN).")
sys.exit(1)
