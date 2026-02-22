"""Data fetcher node — calls Tier 1 parameterized query tools."""

import logging
import time
from datetime import date

from agent.state import SentryState
from agent.tools.batch_tools import get_batch_progress, get_batch_status
from agent.tools.task_tools import get_task_details

log = logging.getLogger(__name__)


def data_fetcher(state: SentryState) -> dict:
    """Execute the appropriate Tier 1 queries based on intent and resolved batch.

    - status_check  → get_batch_status + get_batch_progress
    - rca_drilldown → get_batch_status (FAILED filter) + get_task_details for failures
    - task_detail   → get_task_details for a specific DAG run from context
    """
    intent = state.get("intent", "status_check")
    business_date = state.get("business_date") or date.today().isoformat()
    processing_type = state.get("processing_type")
    dataset_ids = state.get("dataset_ids") or []
    batch_def = state.get("batch_definition")
    tool_calls_log = list(state.get("tool_calls_log") or [])

    query_results: dict = {}
    rca_findings: dict = {}

    if intent == "status_check":
        query_results, rca_findings = _fetch_status(
            dataset_ids, batch_def, business_date, processing_type, tool_calls_log
        )

    elif intent == "rca_drilldown":
        query_results, rca_findings = _fetch_rca(
            dataset_ids, batch_def, business_date, processing_type, tool_calls_log
        )

    elif intent == "task_detail":
        query_results = _fetch_task_detail(state, tool_calls_log)

    return {
        "query_results": query_results,
        "rca_findings": rca_findings if rca_findings else state.get("rca_findings"),
        "tool_calls_log": tool_calls_log,
    }


def _fetch_status(
    dataset_ids: list[str],
    batch_def: dict | None,
    business_date: str,
    processing_type: str | None,
    tool_calls_log: list,
) -> tuple[dict, dict]:
    """Fetch batch status + sequence progress."""
    query_results: dict = {}
    rca_findings: dict = {}

    # 1. Batch status (latest run per dataset + trigger_type)
    t0 = time.time()
    status = get_batch_status(
        dataset_ids=dataset_ids,
        business_date=business_date,
        processing_type=processing_type,
    )
    tool_calls_log.append({
        "tool": "get_batch_status",
        "input": {
            "dataset_ids": dataset_ids,
            "business_date": business_date,
            "processing_type": processing_type,
        },
        "duration_ms": int((time.time() - t0) * 1000),
    })
    query_results["batch_status"] = status

    # 2. Sequence-aware progress (needs batch_def)
    if batch_def:
        t0 = time.time()
        progress = get_batch_progress(
            essential_def=batch_def,
            business_date=business_date,
            processing_type=processing_type,
        )
        tool_calls_log.append({
            "tool": "get_batch_progress",
            "input": {
                "essential_def": batch_def.get("essential_name", ""),
                "business_date": business_date,
            },
            "duration_ms": int((time.time() - t0) * 1000),
        })
        query_results["batch_progress"] = progress

    # 3. If any failures detected, capture RCA context
    failed_rows = [
        r for r in status.get("rows", []) if r.get("STATUS") == "FAILED"
    ]
    if failed_rows:
        rca_findings["failed_datasets"] = []
        for row in failed_rows[:5]:  # Limit to 5 failures for RCA
            dag_run_id = row.get("DAG_RUN_ID", "")
            finding: dict = {
                "dataset_id": row.get("OUTPUT_DATASET_ID"),
                "dag_run_id": dag_run_id,
                "status": row.get("STATUS"),
                "created_date": str(row.get("CREATED_DATE", "")),
                "updated_date": str(row.get("UPDATED_DATE", "")),
            }

            # Fetch task details for the failed DAG run
            if dag_run_id:
                t0 = time.time()
                tasks = get_task_details(dag_run_id, state_filter=["failed"])
                tool_calls_log.append({
                    "tool": "get_task_details",
                    "input": {"dag_run_id": dag_run_id, "state_filter": ["failed"]},
                    "duration_ms": int((time.time() - t0) * 1000),
                })
                finding["failed_tasks"] = tasks.get("tasks", [])

            rca_findings["failed_datasets"].append(finding)

    return query_results, rca_findings


def _fetch_rca(
    dataset_ids: list[str],
    batch_def: dict | None,
    business_date: str,
    processing_type: str | None,
    tool_calls_log: list,
) -> tuple[dict, dict]:
    """Fetch batch status filtered to failures + task details for each."""
    query_results: dict = {}
    rca_findings: dict = {"failed_datasets": []}

    # Get all statuses first (need the full picture)
    t0 = time.time()
    status = get_batch_status(
        dataset_ids=dataset_ids,
        business_date=business_date,
        processing_type=processing_type,
    )
    tool_calls_log.append({
        "tool": "get_batch_status",
        "input": {
            "dataset_ids": dataset_ids,
            "business_date": business_date,
            "processing_type": processing_type,
        },
        "duration_ms": int((time.time() - t0) * 1000),
    })
    query_results["batch_status"] = status

    # Drill into failures
    failed_rows = [
        r for r in status.get("rows", []) if r.get("STATUS") == "FAILED"
    ]
    for row in failed_rows[:10]:
        dag_run_id = row.get("DAG_RUN_ID", "")
        finding: dict = {
            "dataset_id": row.get("OUTPUT_DATASET_ID"),
            "dag_run_id": dag_run_id,
            "status": row.get("STATUS"),
            "processing_type": row.get("processing_type"),
            "created_date": str(row.get("CREATED_DATE", "")),
            "updated_date": str(row.get("UPDATED_DATE", "")),
        }

        if dag_run_id:
            t0 = time.time()
            tasks = get_task_details(dag_run_id)
            tool_calls_log.append({
                "tool": "get_task_details",
                "input": {"dag_run_id": dag_run_id},
                "duration_ms": int((time.time() - t0) * 1000),
            })
            finding["all_tasks"] = tasks.get("tasks", [])
            finding["failed_tasks"] = [
                t for t in tasks.get("tasks", []) if t.get("state") == "failed"
            ]
            finding["task_summary"] = tasks.get("summary", {})

        rca_findings["failed_datasets"].append(finding)

    if not failed_rows:
        rca_findings["message"] = "No failed runs found for this batch and date."

    return query_results, rca_findings


def _fetch_task_detail(state: SentryState, tool_calls_log: list) -> dict:
    """Fetch task details for a specific DAG run.

    The DAG_RUN_ID can come from:
    1. Explicit mention in the user message
    2. Previous query results (e.g. user said "show tasks" after a status check)
    """
    query_results: dict = {}

    # Try to find a DAG_RUN_ID from previous results
    dag_run_id = _extract_dag_run_id(state)
    if not dag_run_id:
        return {"error": "No DAG run ID found. Please specify which run to inspect."}

    t0 = time.time()
    tasks = get_task_details(dag_run_id)
    tool_calls_log.append({
        "tool": "get_task_details",
        "input": {"dag_run_id": dag_run_id},
        "duration_ms": int((time.time() - t0) * 1000),
    })

    query_results["task_details"] = tasks
    query_results["dag_run_id"] = dag_run_id
    return query_results


def _extract_dag_run_id(state: SentryState) -> str | None:
    """Try to extract a DAG_RUN_ID from the user message or prior results."""
    # Check messages for an explicit DAG_RUN_ID (starts with "FGW_")
    for msg in reversed(state.get("messages", [])):
        content = msg.content if hasattr(msg, "content") else str(msg)
        if "FGW_" in content:
            # Extract the FGW_ token
            for token in content.split():
                if token.startswith("FGW_"):
                    return token.rstrip(".,;:!?\"')")

    # Check previous query results for a failed run's DAG_RUN_ID
    prev_results = state.get("query_results") or {}
    batch_status = prev_results.get("batch_status", {})
    for row in batch_status.get("rows", []):
        if row.get("STATUS") == "FAILED" and row.get("DAG_RUN_ID"):
            return row["DAG_RUN_ID"]

    # Check RCA findings
    rca = state.get("rca_findings") or {}
    for finding in rca.get("failed_datasets", []):
        if finding.get("dag_run_id"):
            return finding["dag_run_id"]

    return None
