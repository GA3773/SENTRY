"""
Database connection service for SENTRY.

Manages SQLAlchemy connection pools for both RDS MySQL databases:
- FINEGRAINED_WORKFLOW (batch/workflow status)
- airflow (DAG and task metadata)

RDS_PASSWORD is an IAM auth token that lasts 6+ hours.
URL.create() passes it as a discrete component — no URL parsing issues.
SSL/TLS is ALWAYS enabled — IAM token auth requires an encrypted connection.
"""

import logging
import os
import ssl

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.pool import QueuePool

load_dotenv()

log = logging.getLogger(__name__)


def create_rds_engine(database: str) -> Engine:
    """Create a READ-ONLY SQLAlchemy connection pool to RDS MySQL via NLB.

    Args:
        database: The database name (e.g. 'FINEGRAINED_WORKFLOW' or 'airflow').

    Returns:
        A configured SQLAlchemy Engine.
    """
    host = os.getenv("RDS_HOST")
    port = os.getenv("RDS_PORT", "6150")
    user = os.getenv("RDS_USER")
    password = os.getenv("RDS_PASSWORD")

    if not all([host, user, password]):
        raise ValueError("RDS_HOST, RDS_USER, and RDS_PASSWORD must be set in .env")

    # URL.create() passes the IAM token as a separate component —
    # no URL parsing issues with :, /, ?, &, @ in the token.
    url = URL.create(
        drivername="mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )

    # SSL/TLS is ALWAYS required — IAM token auth is rejected without it.
    # If a PEM CA cert is available, use it for full verification.
    # Otherwise, still enable TLS but skip certificate verification.
    pem_path = os.getenv("RDS_PEM_PATH")
    if pem_path and os.path.exists(pem_path):
        ssl_context = ssl.create_default_context(cafile=pem_path)
        log.info("SSL enabled with CA cert: %s", pem_path)
    else:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        log.info("SSL enabled without cert verification (no PEM file)")

    connect_args = {"ssl": ssl_context}

    engine = create_engine(
        url,
        connect_args=connect_args,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=18000,     # IAM token lasts 6+ hrs; recycle at 5 hrs
        pool_pre_ping=True,     # Verify connection is alive before checkout
        echo=False,
    )

    log.info("Created RDS engine for database: %s", database)
    return engine


# ---------------------------------------------------------------------------
# Module-level engines — import these from other modules
# ---------------------------------------------------------------------------

def get_fgw_engine() -> Engine:
    """Return the FINEGRAINED_WORKFLOW engine (created on first call)."""
    global _fgw_engine
    if _fgw_engine is None:
        _fgw_engine = create_rds_engine(
            os.getenv("FGW_DATABASE", "FINEGRAINED_WORKFLOW")
        )
    return _fgw_engine


def get_airflow_engine() -> Engine:
    """Return the airflow engine (created on first call)."""
    global _airflow_engine
    if _airflow_engine is None:
        _airflow_engine = create_rds_engine(
            os.getenv("AIRFLOW_DATABASE", "airflow")
        )
    return _airflow_engine


_fgw_engine: Engine | None = None
_airflow_engine: Engine | None = None
