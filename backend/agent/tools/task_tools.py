from __future__ import annotations

"""
Tier 1 parameterized query tool for Airflow task details.

Queries airflow.task_instance to drill down from "DAG failed" to
"which specific task failed."

CRITICAL: The join key is run_id (in airflow) = DAG_RUN_ID (in WORKFLOW_RUN_INSTANCE).
"""

import logging
from typing import Optional

from sqlalchemy import text

from config.domain_rules import DEFAULT_QUERY_LIMIT, QUERY_TIMEOUT_SECONDS
from services.db_service import get_airflow_engine

log = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


def get_task_details(
    dag_run_id: str,
    state_filter: Optional[list[str]] = None,
) -> dict:
    """Get task-level details from airflow.task_instance for a specific DAG run.

    Args:
        dag_run_id: The DAG_RUN_ID from WORKFLOW_RUN_INSTANCE (joins to run_id).
        state_filter: Optional list of task states ['failed', 'running'].

    Returns:
        Dict with 'tasks' (list of task dicts ordered by start_date) and
        'summary' (counts by state).
    """
    if not dag_run_id:
        return {"tasks": [], "summary": {}, "total": 0}

    params: dict = {"run_id": dag_run_id}

    query_str = """
        SELECT task_id, dag_id, state, duration, start_date, end_date,
               try_number, hostname, operator
        FROM task_instance
        WHERE run_id = :run_id
    """

    if state_filter:
        sf_placeholders = ", ".join(
            [f":sf_{i}" for i in range(len(state_filter))]
        )
        query_str += f" AND state IN ({sf_placeholders})"
        for i, sf in enumerate(state_filter):
            params[f"sf_{i}"] = sf

    query_str += " ORDER BY start_date LIMIT :lim"
    params["lim"] = DEFAULT_QUERY_LIMIT

    engine = get_airflow_engine()
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(timeout=QUERY_TIMEOUT_SECONDS)
            result = conn.execute(text(query_str), params)
            rows = [_row_to_dict(r) for r in result]
    except Exception as e:
        log.error("get_task_details failed: %s", e)
        return {"tasks": [], "summary": {}, "total": 0, "error": str(e)}

    # Build summary counts by state
    summary: dict[str, int] = {}
    for row in rows:
        state = row.get("state", "unknown")
        summary[state] = summary.get(state, 0) + 1

    # Convert datetime objects to strings for JSON serialization
    for row in rows:
        for key in ("start_date", "end_date"):
            if row.get(key) is not None:
                row[key] = str(row[key])

    return {"tasks": rows, "summary": summary, "total": len(rows)}
