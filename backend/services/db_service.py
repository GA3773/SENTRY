"""
Database connection service for SENTRY.

Manages SQLAlchemy connection pools for both RDS MySQL databases:
- FINEGRAINED_WORKFLOW (batch/workflow status)
- airflow (DAG and task metadata)

RDS_PASSWORD is an IAM auth token that expires in ~15 minutes.
URL.create() passes it as a discrete component — no URL parsing issues.
SSL is optional: only enabled if RDS_PEM_PATH is set and the file exists.
"""

import logging
import os

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

    # SSL is optional — only add ssl context if RDS_PEM_PATH is set
    # and the file exists. The NLB endpoint may not require a cert.
    connect_args: dict = {}
    pem_path = os.getenv("RDS_PEM_PATH")
    if pem_path and os.path.exists(pem_path):
        import ssl

        ssl_context = ssl.create_default_context(cafile=pem_path)
        connect_args["ssl"] = ssl_context
        log.info("SSL enabled using PEM: %s", pem_path)
    else:
        log.info("SSL disabled — RDS_PEM_PATH not set or file not found")

    engine = create_engine(
        url,
        connect_args=connect_args,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=600,       # IAM token expires in ~15 min; recycle well before
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
