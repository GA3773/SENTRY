from __future__ import annotations

"""
Tier 1 parameterized query tools for batch/workflow monitoring.

These tools query FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE.
The LLM's job is parameter extraction — these tools handle the SQL.

CRITICAL RULES:
- Every query MUST filter on business_date (indexed column).
- Every query MUST have LIMIT (default 500).
- All SQL uses parameterized %s placeholders — NEVER f-strings.
- TRIGGER_TYPE mapping is absolute: ProcessTrigger=PRELIM, RerunTrigger=FINAL.
"""

import logging
from typing import Optional

from sqlalchemy import text

from config.domain_rules import (
    DEFAULT_QUERY_LIMIT,
    QUERY_TIMEOUT_SECONDS,
    TRIGGER_TYPE_MAP,
    TRIGGER_TYPE_REVERSE,
)
from services.db_service import get_fgw_engine

log = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


def get_batch_status(
    dataset_ids: list[str],
    business_date: str,
    processing_type: Optional[str] = None,
    status_filter: Optional[list[str]] = None,
    limit: int = DEFAULT_QUERY_LIMIT,
) -> dict:
    """Get workflow status for a batch's datasets from WORKFLOW_RUN_INSTANCE.

    Uses ROW_NUMBER() to return only the latest run per dataset+trigger_type.

    Args:
        dataset_ids: List of output_dataset_ids (from Lenz API).
        business_date: Date string YYYY-MM-DD.
        processing_type: 'PRELIM', 'FINAL', 'MANUAL', or None for all.
        status_filter: Optional list of statuses ['SUCCESS', 'FAILED', etc.].
        limit: Max rows (default 500).

    Returns:
        Dict with 'rows' (list of result dicts) and 'summary' (counts by status).
    """
    if not dataset_ids:
        return {"rows": [], "summary": {}, "total": 0}

    limit = min(limit, DEFAULT_QUERY_LIMIT)

    # Build parameterized IN clause
    placeholders = ", ".join([":ds_" + str(i) for i in range(len(dataset_ids))])
    params: dict = {"bdate": business_date}
    for i, ds_id in enumerate(dataset_ids):
        params[f"ds_{i}"] = ds_id

    # Use ROW_NUMBER to get latest run per dataset + trigger_type
    inner_where = (
        f"WHERE business_date = :bdate AND output_dataset_id IN ({placeholders})"
    )

    if processing_type and processing_type.upper() in TRIGGER_TYPE_MAP:
        inner_where += " AND TRIGGER_TYPE = :trigger"
        params["trigger"] = TRIGGER_TYPE_MAP[processing_type.upper()]

    query_str = f"""
        SELECT * FROM (
            SELECT WORKFLOW_RUN_INSTANCE_KEY, WORKFLOW_ID, DAG_ID, DAG_RUN_ID,
                   STATUS, STATUS_DETAIL, TRIGGER_TYPE, CREATED_DATE, UPDATED_DATE,
                   OUTPUT_DATASET_ID, BUSINESS_DATE,
                   ROW_NUMBER() OVER(
                       PARTITION BY OUTPUT_DATASET_ID, TRIGGER_TYPE
                       ORDER BY CREATED_DATE DESC
                   ) AS rn
            FROM WORKFLOW_RUN_INSTANCE
            {inner_where}
        ) ranked
        WHERE rn = 1
    """

    if status_filter:
        sf_placeholders = ", ".join(
            [":sf_" + str(i) for i in range(len(status_filter))]
        )
        query_str += f" AND STATUS IN ({sf_placeholders})"
        for i, sf in enumerate(status_filter):
            params[f"sf_{i}"] = sf

    query_str += " ORDER BY CREATED_DATE DESC LIMIT :lim"
    params["lim"] = limit

    engine = get_fgw_engine()
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(
                timeout=QUERY_TIMEOUT_SECONDS
            )
            result = conn.execute(text(query_str), params)
            rows = [_row_to_dict(r) for r in result]
    except Exception as e:
        log.error("get_batch_status failed: %s", e)
        return {"rows": [], "summary": {}, "total": 0, "error": str(e)}

    # Build summary counts
    summary: dict[str, int] = {}
    for row in rows:
        status = row.get("STATUS", "UNKNOWN")
        summary[status] = summary.get(status, 0) + 1

    # Map trigger types to human-readable names
    for row in rows:
        row["processing_type"] = TRIGGER_TYPE_REVERSE.get(
            row.get("TRIGGER_TYPE", ""), row.get("TRIGGER_TYPE", "")
        )

    return {"rows": rows, "summary": summary, "total": len(rows)}


def get_slice_status(
    dataset_id: str,
    business_date: str,
    slice_patterns: list[str],
    processing_type: Optional[str] = None,
) -> dict:
    """Get status for specific slices of a dataset by filtering DAG_RUN_ID patterns.

    Args:
        dataset_id: Exact output_dataset_id.
        business_date: Date string YYYY-MM-DD.
        slice_patterns: List of slice name substrings to match in DAG_RUN_ID.
            These MUST come from the Lenz API, not from parsing DAG_RUN_IDs.
        processing_type: 'PRELIM', 'FINAL', or None for all.

    Returns:
        Dict with per-slice status including latest run for each slice.
    """
    if not slice_patterns:
        return {"slices": {}, "total": 0}

    # Build LIKE conditions for each slice pattern — one OR'd clause per slice.
    # Each slice gets its own subquery via ROW_NUMBER so we get the latest run per slice.
    like_clauses = []
    params: dict = {"bdate": business_date, "ds_id": dataset_id}
    for i, pattern in enumerate(slice_patterns):
        like_clauses.append(f"dag_run_id LIKE :sp_{i}")
        params[f"sp_{i}"] = f"%{pattern}%"

    like_where = " OR ".join(like_clauses)

    trigger_clause = ""
    if processing_type and processing_type.upper() in TRIGGER_TYPE_MAP:
        trigger_clause = " AND TRIGGER_TYPE = :trigger"
        params["trigger"] = TRIGGER_TYPE_MAP[processing_type.upper()]

    query_str = f"""
        SELECT WORKFLOW_RUN_INSTANCE_KEY, WORKFLOW_ID, DAG_ID, DAG_RUN_ID,
               STATUS, STATUS_DETAIL, TRIGGER_TYPE, CREATED_DATE, UPDATED_DATE,
               OUTPUT_DATASET_ID, BUSINESS_DATE
        FROM WORKFLOW_RUN_INSTANCE
        WHERE business_date = :bdate
          AND output_dataset_id = :ds_id
          AND ({like_where})
          {trigger_clause}
        ORDER BY CREATED_DATE DESC
        LIMIT :lim
    """
    params["lim"] = DEFAULT_QUERY_LIMIT

    engine = get_fgw_engine()
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(timeout=QUERY_TIMEOUT_SECONDS)
            result = conn.execute(text(query_str), params)
            rows = [_row_to_dict(r) for r in result]
    except Exception as e:
        log.error("get_slice_status failed: %s", e)
        return {"slices": {}, "total": 0, "error": str(e)}

    # Group rows by slice pattern. A row matches a slice if its DAG_RUN_ID
    # contains the slice pattern substring.
    slices: dict[str, list[dict]] = {p: [] for p in slice_patterns}
    for row in rows:
        dag_run_id = row.get("DAG_RUN_ID", "")
        row["processing_type"] = TRIGGER_TYPE_REVERSE.get(
            row.get("TRIGGER_TYPE", ""), row.get("TRIGGER_TYPE", "")
        )
        for pattern in slice_patterns:
            if pattern in dag_run_id:
                slices[pattern].append(row)
                break  # each row belongs to one slice

    # For each slice, find the latest run
    slice_summary: dict[str, dict] = {}
    for pattern, pattern_rows in slices.items():
        if pattern_rows:
            # Rows are already ordered by CREATED_DATE DESC
            latest = pattern_rows[0]
            slice_summary[pattern] = {
                "status": latest.get("STATUS"),
                "processing_type": latest.get("processing_type"),
                "created_date": str(latest.get("CREATED_DATE", "")),
                "updated_date": str(latest.get("UPDATED_DATE", "")),
                "dag_run_id": latest.get("DAG_RUN_ID"),
                "total_runs": len(pattern_rows),
            }
        else:
            slice_summary[pattern] = {
                "status": "NOT_STARTED",
                "total_runs": 0,
            }

    return {"slices": slice_summary, "total": len(rows)}


def get_batch_progress(
    essential_def: dict,
    business_date: str,
    processing_type: Optional[str] = None,
) -> dict:
    """Get sequence-aware progress for a batch.

    Uses the Lenz definition to group datasets by sequence order and report
    completion status per step.

    Args:
        essential_def: Serialized EssentialDef dict with 'datasets' containing
            'dataset_id' and 'sequence_order' fields.
        business_date: Date string YYYY-MM-DD.
        processing_type: 'PRELIM', 'FINAL', or None for all.

    Returns:
        Dict with per-sequence-step status and overall progress fraction.
    """
    datasets = essential_def.get("datasets", [])
    if not datasets:
        return {"steps": [], "overall": {"completed": 0, "total": 0, "fraction": 0.0}}

    all_dataset_ids = [d["dataset_id"] for d in datasets]

    # Fetch status for all datasets in one query
    status_result = get_batch_status(
        dataset_ids=all_dataset_ids,
        business_date=business_date,
        processing_type=processing_type,
    )

    if status_result.get("error"):
        return {
            "steps": [],
            "overall": {"completed": 0, "total": 0, "fraction": 0.0},
            "error": status_result["error"],
        }

    # Index rows by dataset_id for fast lookup
    status_by_dataset: dict[str, dict] = {}
    for row in status_result["rows"]:
        ds_id = row.get("OUTPUT_DATASET_ID", "")
        # Keep the first (latest) row per dataset
        if ds_id not in status_by_dataset:
            status_by_dataset[ds_id] = row

    # Group datasets by sequence order
    sequence_groups: dict[int, list[dict]] = {}
    for d in datasets:
        seq = d.get("sequence_order", 0)
        sequence_groups.setdefault(seq, []).append(d)

    steps = []
    total_datasets = len(all_dataset_ids)
    completed_datasets = 0

    for seq_order in sorted(sequence_groups.keys()):
        group_datasets = sequence_groups[seq_order]
        step_statuses = []

        for d in group_datasets:
            ds_id = d["dataset_id"]
            run = status_by_dataset.get(ds_id)
            if run:
                step_statuses.append(run.get("STATUS", "UNKNOWN"))
            else:
                step_statuses.append("NOT_STARTED")

        success_count = step_statuses.count("SUCCESS")
        failed_count = step_statuses.count("FAILED")
        running_count = step_statuses.count("RUNNING")
        not_started_count = step_statuses.count("NOT_STARTED")

        completed_datasets += success_count

        # Determine step-level status
        if all(s == "SUCCESS" for s in step_statuses):
            step_status = "COMPLETED"
        elif failed_count > 0:
            step_status = "FAILED"
        elif running_count > 0:
            step_status = "RUNNING"
        elif not_started_count == len(step_statuses):
            step_status = "NOT_STARTED"
        else:
            step_status = "PARTIAL"

        steps.append({
            "sequence_order": seq_order,
            "status": step_status,
            "datasets": [d["dataset_id"] for d in group_datasets],
            "counts": {
                "success": success_count,
                "failed": failed_count,
                "running": running_count,
                "not_started": not_started_count,
                "total": len(step_statuses),
            },
        })

    fraction = completed_datasets / total_datasets if total_datasets > 0 else 0.0

    return {
        "steps": steps,
        "overall": {
            "completed": completed_datasets,
            "total": total_datasets,
            "fraction": round(fraction, 4),
        },
    }


def get_historical_runs(
    dataset_id: str,
    last_n_business_dates: int = 10,
    processing_type: Optional[str] = None,
) -> dict:
    """Get historical run data for trend analysis and runtime prediction.

    Queries across multiple recent business dates to compute runtime stats.
    Only includes completed runs (SUCCESS) for runtime calculations.

    Args:
        dataset_id: Exact output_dataset_id.
        last_n_business_dates: How many recent business dates to query (default 10).
        processing_type: 'PRELIM', 'FINAL', or None for all.

    Returns:
        Dict with per-business-date runtime stats.
    """
    last_n_business_dates = min(last_n_business_dates, 30)

    params: dict = {"ds_id": dataset_id, "n_dates": last_n_business_dates}

    trigger_clause = ""
    if processing_type and processing_type.upper() in TRIGGER_TYPE_MAP:
        trigger_clause = " AND TRIGGER_TYPE = :trigger"
        params["trigger"] = TRIGGER_TYPE_MAP[processing_type.upper()]

    # First, get the N most recent distinct business dates for this dataset
    dates_query = f"""
        SELECT DISTINCT business_date
        FROM WORKFLOW_RUN_INSTANCE
        WHERE output_dataset_id = :ds_id
          AND STATUS = 'SUCCESS'
          {trigger_clause}
        ORDER BY business_date DESC
        LIMIT :n_dates
    """

    # Then fetch all SUCCESS runs for those dates
    query_str = f"""
        SELECT OUTPUT_DATASET_ID, DAG_RUN_ID, STATUS, TRIGGER_TYPE,
               BUSINESS_DATE, CREATED_DATE, UPDATED_DATE,
               TIMESTAMPDIFF(MINUTE, CREATED_DATE, UPDATED_DATE) AS duration_minutes
        FROM WORKFLOW_RUN_INSTANCE
        WHERE output_dataset_id = :ds_id
          AND STATUS = 'SUCCESS'
          AND business_date IN ({dates_query})
          {trigger_clause}
        ORDER BY BUSINESS_DATE DESC, CREATED_DATE DESC
        LIMIT :lim
    """
    params["lim"] = DEFAULT_QUERY_LIMIT

    engine = get_fgw_engine()
    try:
        with engine.connect() as conn:
            conn = conn.execution_options(timeout=QUERY_TIMEOUT_SECONDS)
            result = conn.execute(text(query_str), params)
            rows = [_row_to_dict(r) for r in result]
    except Exception as e:
        log.error("get_historical_runs failed: %s", e)
        return {"history": [], "stats": {}, "error": str(e)}

    # Group by business_date and compute stats
    by_date: dict[str, list[int]] = {}
    for row in rows:
        bdate = str(row.get("BUSINESS_DATE", ""))
        dur = row.get("duration_minutes")
        if dur is not None:
            by_date.setdefault(bdate, []).append(int(dur))

    history = []
    all_durations: list[int] = []
    for bdate in sorted(by_date.keys(), reverse=True):
        durations = by_date[bdate]
        all_durations.extend(durations)
        history.append({
            "business_date": bdate,
            "run_count": len(durations),
            "min_minutes": min(durations),
            "max_minutes": max(durations),
            "avg_minutes": round(sum(durations) / len(durations), 1),
        })

    # Overall stats
    stats: dict = {}
    if all_durations:
        sorted_dur = sorted(all_durations)
        n = len(sorted_dur)
        stats = {
            "p50_minutes": sorted_dur[n // 2],
            "p90_minutes": sorted_dur[int(n * 0.9)],
            "p95_minutes": sorted_dur[int(n * 0.95)],
            "avg_minutes": round(sum(sorted_dur) / n, 1),
            "sample_count": n,
        }

    return {"history": history, "stats": stats}
