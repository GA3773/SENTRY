# SENTRY Connectivity Details

## RDS MySQL Connection

Connection pattern follows: https://raw.githubusercontent.com/GA3773/Comm/refs/heads/main/backend/db.py

SENTRY runs locally for Phase 1. RDS connectivity details (host, port, user, password, PEM file) will be provided separately and stored as environment variables — NEVER hardcode.

### IAM Token Authentication

The RDS password is NOT a static password — it's an **IAM authentication token** generated via:
```bash
aws rds generate-db-auth-token \
    --hostname <rds-host> \
    --port 6150 \
    --username AuroraReadWrite \
    --region us-east-1
```

**Token lifetime: 6+ hours.** Regenerate and re-paste into `.env` when it eventually expires. When connections start failing with auth errors, regenerate the token.

**CRITICAL: Wrap in single quotes in .env** — the token contains `&`, `=`, `%`, `?` characters that will break without quoting:
```
RDS_PASSWORD='fgwrds-prod-node-0...&X-Amz-Algorithm=AWS4-HMAC-SHA256&...'
```

The password must also be **URL-encoded** when building the SQLAlchemy connection string, since it contains special characters:

```python
# .env (NEVER commit this file)
RDS_HOST=<provided>
RDS_PORT=6150
RDS_USER=AuroraReadWrite
RDS_PASSWORD='<iam-token-in-single-quotes>'
RDS_PEM_PATH=rds.pem
FGW_DATABASE=FINEGRAINED_WORKFLOW
AIRFLOW_DATABASE=airflow
```

### Connection Implementation
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import QueuePool

def create_rds_engine(database: str):
    """Create a READ-ONLY connection pool to RDS MySQL via NLB."""
    
    # Use URL.create() — NEVER build URL via f-string.
    # The IAM token password contains :, /, ?, &, @ characters that break URL parsing
    # even with quote_plus(). URL.create() passes credentials as separate components.
    url = URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("RDS_USER"),
        password=os.getenv("RDS_PASSWORD"),  # raw IAM token, no encoding needed
        host=os.getenv("RDS_HOST"),           # NLB endpoint, NOT raw RDS node
        port=int(os.getenv("RDS_PORT", "6150")),
        database=database,
    )
    
    # SSL/TLS is MANDATORY for IAM token auth — without it MySQL rejects the token
    # and pymysql reports "using password: NO".
    # If a PEM CA cert is provided, use it for full verification.
    # Otherwise, still enable TLS but skip certificate verification.
    import ssl

    pem_path = os.getenv("RDS_PEM_PATH")
    if pem_path and os.path.exists(pem_path):
        ssl_context = ssl.create_default_context(cafile=pem_path)
    else:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    connect_args = {"ssl": ssl_context}

    engine = create_engine(
        url,
        connect_args=connect_args,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=18000, # Recycle connections every 5 hrs (token lasts 6+ hrs)
        pool_pre_ping=True, # Verify connection is alive before using
        echo=False
    )
    return engine

# Create two engines — one per database
fgw_engine = create_rds_engine("FINEGRAINED_WORKFLOW")
airflow_engine = create_rds_engine("airflow")
```

### Key Decisions
- **Host is the NLB endpoint** (`nlb-qomo-...elb.us-east-1.amazonaws.com`), NOT the raw RDS node (`fgwrds-prod-node-0...rds.amazonaws.com`). The raw node may not be reachable from local.
- **URL.create() is mandatory** — f-string URL building breaks even with `quote_plus()` because the IAM token can contain `%`, `@`, and other sequences that SQLAlchemy's URL parser misinterprets.
- **SSL/TLS is mandatory** — IAM token auth requires an encrypted connection. Without TLS, MySQL rejects the token and pymysql reports "using password: NO". If `RDS_PEM_PATH` is set, full cert verification is used. Otherwise, TLS is still enabled but without cert verification (same as MySQL Workbench auto-negotiation).

### CRITICAL: All connections must be READ-ONLY
Use a MySQL user with SELECT-only privileges. If not available, the application code must enforce read-only at the query validation layer (see @docs/query-tier-system.md).

## Azure OpenAI Connection

Connection pattern follows EXACTLY: https://raw.githubusercontent.com/GA3773/COST_AGENT_AWS/refs/heads/main/services/azure_openai.py

Uses **hybrid authentication**: SPN certificate for Bearer token + API key. Both are sent on every request. A fresh client with a fresh token is created per graph invocation to avoid token expiry.

```python
# .env
AZURE_TENANT_ID=<provided>
AZURE_SPN_CLIENT_ID=<provided>
AZURE_PEM_PATH=<path_to_spn_cert.pem>
AZURE_OPENAI_API_KEY=<provided>
AZURE_OPENAI_ENDPOINT=<provided>
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=<provided>
AZURE_USER_ID=<provided>
```

### Authentication Pattern (EXACT — copy this structure)

```python
"""Azure OpenAI client factory with hybrid authentication.

Authentication flow:
1. Service Principal authenticates with Azure AD using PEM certificate
2. Azure AD returns an access token
3. Access token is sent as Bearer token in Authorization header
4. OpenAI API key is ALSO sent for authentication
5. A fresh client with fresh token is created for each graph invocation
"""

import os
from datetime import datetime
from azure.identity import CertificateCredential
from langchain_openai import AzureChatOpenAI

logger = logging.getLogger(__name__)

# Cached credential object (thread-safe, handles token caching internally)
_credential = None


def _get_credential() -> CertificateCredential | None:
    """Get or create the CertificateCredential for Azure AD authentication."""
    global _credential
    if _credential is not None:
        return _credential

    tenant_id = os.getenv('AZURE_TENANT_ID')
    client_id = os.getenv('AZURE_SPN_CLIENT_ID')
    pem_path = os.getenv('AZURE_PEM_PATH')

    if not tenant_id or not client_id:
        logger.warning("Azure Service Principal credentials not configured")
        return None

    if not os.path.exists(pem_path):
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
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-01')
    deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
    user_id = os.getenv('AZURE_USER_ID', '')

    if not endpoint or not api_key:
        raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set")

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
```

### CRITICAL USAGE NOTE
**Call `create_llm()` before each graph invocation** — do NOT cache the LLM instance globally. The Bearer token expires, so a fresh client ensures a fresh token. The `CertificateCredential` itself IS cached (module-level singleton), so re-creating the LLM is cheap — only the token refresh + LLM object creation happens, not a full re-auth.

## Lenz API Connection

The Lenz API is behind JPMC's ADFS (Active Directory Federation Services) authentication, using Windows Integrated Authentication (NTLM).

```python
# .env
LENZ_API_BASE_URL=https://lenz-app.prod.aws.jpmchase.net/lenz/essentials
LENZ_USERNAME=<JPMC SID — e.g. I792420>
LENZ_PASSWORD=<JPMC password>
LENZ_CACHE_TTL=300
```

### Authentication Pattern

Primary approach — async httpx with NTLM:
```python
import os
import httpx
from httpx_ntlm import HttpNtlmAuth

async def fetch_essential_def(essential_name: str) -> dict:
    """Fetch essential definition from Lenz API with NTLM auth."""
    auth = HttpNtlmAuth(os.getenv("LENZ_USERNAME"), os.getenv("LENZ_PASSWORD"))
    
    async with httpx.AsyncClient(auth=auth, timeout=30, follow_redirects=True) as client:
        response = await client.get(
            f"{os.getenv('LENZ_API_BASE_URL')}/def",
            params={"name": essential_name}
        )
        response.raise_for_status()
        return response.json()
```

**If `httpx-ntlm` doesn't work** (some ADFS configs reject async NTLM), fall back to sync `requests` + `requests-ntlm`:

```python
import requests
from requests_ntlm import HttpNtlmAuth as RequestsNtlmAuth

def fetch_essential_def_sync(essential_name: str) -> dict:
    """Sync fallback using requests + NTLM."""
    auth = RequestsNtlmAuth(os.getenv("LENZ_USERNAME"), os.getenv("LENZ_PASSWORD"))
    response = requests.get(
        f"{os.getenv('LENZ_API_BASE_URL')}/def",
        params={"name": essential_name},
        auth=auth,
        timeout=30,
        verify=True
    )
    response.raise_for_status()
    return response.json()
```

**Note:** Lenz calls are infrequent (cached with 5-min TTL), so using sync fallback has negligible performance impact. If async NTLM fails during testing, switch to sync — do NOT block on this.

## AWS CloudWatch Connection (FUTURE — Phase 4)

NOT part of current implementation. AWS resource names (RDS instance ID, SQS queue names) have not been provided yet. This section is a placeholder for when AWS diagnostics phase begins.

Prerequisites before implementing:
- RDS instance identifier for CloudWatch metrics
- SQS queue name(s) to monitor
- AWS credentials with CloudWatch read access
- Clarity on which specific metrics matter for RCA

```python
# Phase 4 only — do NOT implement until resource names are provided
# .env additions when ready:
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# RDS_INSTANCE_ID=
# SQS_QUEUE_NAME=
```

## Environment Variable Template

Create a `.env.example` file (commit this, not `.env`):
```
# RDS MySQL (IAM Token Auth — password expires in ~15 min, regenerate with aws rds generate-db-auth-token)
# CRITICAL: Wrap RDS_PASSWORD in single quotes — token contains &, =, %, ? characters
# RDS_HOST is the NLB endpoint, NOT the raw RDS node
RDS_HOST=
RDS_PORT=6150
RDS_USER=AuroraReadWrite
RDS_PASSWORD=''
RDS_PEM_PATH=rds.pem
FGW_DATABASE=FINEGRAINED_WORKFLOW
AIRFLOW_DATABASE=airflow

# Azure OpenAI (Hybrid Auth: SPN Certificate + API Key)
AZURE_TENANT_ID=
AZURE_SPN_CLIENT_ID=
AZURE_PEM_PATH=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=
AZURE_USER_ID=

# Lenz API (NTLM auth via ADFS)
LENZ_API_BASE_URL=https://lenz-app.prod.aws.jpmchase.net/lenz/essentials
LENZ_USERNAME=
LENZ_PASSWORD=

# App
LOG_LEVEL=INFO
LENZ_CACHE_TTL=300
QUERY_TIMEOUT=10
MAX_QUERY_ROWS=500

# Phase 2+ (uncomment when needed)
# REDIS_URL=redis://localhost:6379/0

# Phase 4 — AWS Diagnostics (uncomment when resource names are provided)
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# RDS_INSTANCE_ID=
# SQS_QUEUE_NAME=
```

