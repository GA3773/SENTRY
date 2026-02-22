"""
Database connection service for SENTRY.

Manages SQLAlchemy connection pools for both RDS MySQL databases:
- FINEGRAINED_WORKFLOW (batch/workflow status)
- airflow (DAG and task metadata)

RDS_PASSWORD is an IAM auth token that expires in ~15 minutes.
It must be URL-encoded in the connection string, and pool_recycle
must be set well below the expiry window.
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


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context using the RDS PEM certificate."""
    pem_path = os.getenv("RDS_PEM_PATH")
    if not pem_path:
        raise ValueError("RDS_PEM_PATH environment variable is not set")
    if not os.path.exists(pem_path):
        raise FileNotFoundError(f"RDS PEM file not found: {pem_path}")
    return ssl.create_default_context(cafile=pem_path)


def create_rds_engine(database: str) -> Engine:
    """Create a READ-ONLY SQLAlchemy connection pool to RDS MySQL.

    Args:
        database: The database name (e.g. 'FINEGRAINED_WORKFLOW' or 'airflow').

    Returns:
        A configured SQLAlchemy Engine.
    """
    host = os.getenv("RDS_HOST")
    port = os.getenv("RDS_PORT", "3306")
    user = os.getenv("RDS_USER")
    password = os.getenv("RDS_PASSWORD")

    if not all([host, user, password]):
        raise ValueError("RDS_HOST, RDS_USER, and RDS_PASSWORD must be set in .env")

    ssl_context = _build_ssl_context()

    # Use URL.create() so the IAM token (which contains :, /, ?, &)
    # is passed as a discrete component — never embedded in a string
    # that SQLAlchemy's URL parser would try to split on delimiters.
    url = URL.create(
        drivername="mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=database,
    )

    engine = create_engine(
        url,
        connect_args={"ssl": ssl_context},
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=600,       # IAM token expires in ~15 min; recycle well before
        pool_pre_ping=True,     # Verify connections before checkout
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
