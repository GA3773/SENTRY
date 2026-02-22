"""Azure OpenAI client factory with hybrid authentication.

Authentication flow:
1. Service Principal authenticates with Azure AD using PEM certificate
2. Azure AD returns an access token
3. Access token is sent as Bearer token in Authorization header
4. OpenAI API key is ALSO sent for authentication
5. A fresh client with fresh token is created for each graph invocation
"""

import logging
import os
from datetime import datetime

from azure.identity import CertificateCredential
from langchain_openai import AzureChatOpenAI

logger = logging.getLogger(__name__)

# Cached credential object (thread-safe, handles token caching internally)
_credential: CertificateCredential | None = None


def _get_credential() -> CertificateCredential | None:
    """Get or create the CertificateCredential for Azure AD authentication."""
    global _credential
    if _credential is not None:
        return _credential

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_SPN_CLIENT_ID")
    pem_path = os.getenv("AZURE_PEM_PATH")

    if not tenant_id or not client_id:
        logger.warning("Azure Service Principal credentials not configured")
        return None

    if not pem_path or not os.path.exists(pem_path):
        logger.warning(f"PEM certificate not found at {pem_path}")
        return None

    try:
        _credential = CertificateCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            certificate_path=pem_path,
        )
        logger.info("CertificateCredential created successfully")
        return _credential
    except Exception as e:
        logger.error(f"Failed to create CertificateCredential: {e}")
        return None


def _get_bearer_token() -> str | None:
    """Get a fresh Azure AD access token for cognitive services."""
    credential = _get_credential()
    if not credential:
        return None

    try:
        token_response = credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        )
        logger.info(
            f"Azure AD token obtained, expires at "
            f"{datetime.fromtimestamp(token_response.expires_on).isoformat()}"
        )
        return token_response.token
    except Exception as e:
        logger.error(f"Failed to get Azure AD token: {e}")
        return None


def create_llm() -> AzureChatOpenAI:
    """Create an AzureChatOpenAI instance with hybrid authentication.

    Uses Service Principal + PEM certificate for Bearer token when available,
    falls back to API key only authentication otherwise.

    Returns a fresh LLM instance with a fresh token (call this before each
    graph invocation to avoid token expiry during long-running workflows).
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    user_id = os.getenv("AZURE_USER_ID", "")

    if not endpoint or not api_key:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set"
        )

    # Build default headers
    default_headers = {"x-ms-useragent": user_id}

    # Try hybrid auth: Bearer token + API key
    bearer_token = _get_bearer_token()
    if bearer_token:
        default_headers["Authorization"] = f"Bearer {bearer_token}"
        logger.info("Creating AzureChatOpenAI with hybrid auth (Bearer + API key)")
    else:
        logger.info("Creating AzureChatOpenAI with API key auth only")

    llm = AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=deployment,
        default_headers=default_headers,
        temperature=0,
    )

    return llm
