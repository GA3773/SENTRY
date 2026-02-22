"""
Static mapping of user-facing batch names to Lenz essential names.

This is the ONLY static config for batch resolution.
Everything else comes from the Lenz API at runtime.
"""

ESSENTIAL_MAP: dict[str, str] = {
    "6G": "6G-FR2052a-E2E",
    "FR2052A": "6G-FR2052a-E2E",
    "PBSYNTHETICS": "PBSynthetics",
    "SNU": "SNU",
    "SNU STRATEGIC": "SNU-Strategic",
    "SNU REG STRATEGIC": "SNU-REG-STRATEGIC",
    "COLLATERAL": "TB-Collateral",
    "DERIVATIVES": "TB-Derivatives",
    "DERIV": "TB-Derivatives",
    "SECURITIES": "TB-Securities",
    "SECFIN": "TB-SecFIn",
    "CFG": "TB-CFG",
    "SMAA": "TB-SMAA",
    "UPC": "UPC",
}
