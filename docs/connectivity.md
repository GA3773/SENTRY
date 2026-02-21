# SENTRY Connectivity Details

## RDS MySQL Connection

Connection pattern follows: https://raw.githubusercontent.com/GA3773/Comm/refs/heads/main/backend/db.py

SENTRY runs locally for Phase 1. RDS connectivity details (host, port, user, password, PEM file) will be provided separately and stored as environment variables — NEVER hardcode.

```python
# .env (NEVER commit this file)
RDS_HOST=<provided>
RDS_PORT=3306
RDS_USER=<provided>
RDS_PASSWORD=<provided>
RDS_PEM_PATH=<path_to_pem_file>
FGW_DATABASE=FINEGRAINED_WORKFLOW
AIRFLOW_DATABASE=airflow
```

### Connection Implementation
```python
import os
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
import ssl

def create_rds_engine(database: str):
    """Create a READ-ONLY connection pool to RDS MySQL."""
    ssl_context = ssl.create_default_context(cafile=os.getenv("RDS_PEM_PATH"))
    
    engine = create_engine(
        f"mysql+pymysql://{os.getenv('RDS_USER')}:{os.getenv('RDS_PASSWORD')}"
        f"@{os.getenv('RDS_HOST')}:{os.getenv('RDS_PORT')}/{database}",
        connect_args={"ssl": ssl_context},
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        echo=False
    )
    return engine

# Create two engines — one per database
fgw_engine = create_rds_engine("FINEGRAINED_WORKFLOW")
airflow_engine = create_rds_engine("airflow")
```

### CRITICAL: All connections must be READ-ONLY
Use a MySQL user with SELECT-only privileges. If not available, the application code must enforce read-only at the query validation layer (see @docs/query-tier-system.md).

## Azure OpenAI Connection

Connection pattern follows: https://raw.githubusercontent.com/GA3773/COST_AGENT_AWS/refs/heads/main/services/azure_openai.py

Use the EXACT same method — do not use direct OpenAI SDK, use Azure-specific endpoint.

```python
# .env
AZURE_OPENAI_API_KEY=<provided>
AZURE_OPENAI_ENDPOINT=<provided>
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=<provided>  # GPT-4o deployment
```

```python
from langchain_openai import AzureChatOpenAI

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    temperature=0,       # Deterministic for SQL and status queries
    max_tokens=4096,
    timeout=30
)
```

## Lenz API Connection

```python
# .env
LENZ_API_BASE_URL=https://lenz-app.prod.aws.jpmchase.net/lenz/essentials
```

No special auth required for Lenz API (assumes network-level access within JPMC network). If auth is needed, add bearer token support.

```python
import httpx

async def fetch_essential_def(essential_name: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{os.getenv('LENZ_API_BASE_URL')}/def",
            params={"name": essential_name}
        )
        response.raise_for_status()
        return response.json()
```

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
# RDS MySQL
RDS_HOST=
RDS_PORT=3306
RDS_USER=
RDS_PASSWORD=
RDS_PEM_PATH=
FGW_DATABASE=FINEGRAINED_WORKFLOW
AIRFLOW_DATABASE=airflow

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=

# Lenz API
LENZ_API_BASE_URL=https://lenz-app.prod.aws.jpmchase.net/lenz/essentials

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
