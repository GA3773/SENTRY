"""Analyzer node — reasons over fetched data to produce structured analysis."""

import logging
from datetime import datetime

from agent.state import SentryState

log = logging.getLogger(__name__)

# Duration thresholds for anomaly detection (minutes)
DURATION_ANOMALY_FACTOR = 2.0  # Flag if > 2x median


def analyzer(state: SentryState) -> dict:
    """Analyze query results: group by sequence, identify failures, compute progress.

    Produces an `analysis` dict consumed by response_synthesizer.
    """
    query_results = state.get("query_results") or {}
    batch_def = state.get("batch_definition")
    rca_findings = state.get("rca_findings") or {}
    intent = state.get("intent", "status_check")

    analysis: dict = {"intent": intent}

    batch_status = query_results.get("batch_status", {})
    batch_progress = query_results.get("batch_progress", {})
    rows = batch_status.get("rows", [])

    # ---- Summary counts ----
    summary = batch_status.get("summary", {})
    analysis["summary"] = {
        "total_datasets": batch_status.get("total", 0),
        "success": summary.get("SUCCESS", 0),
        "failed": summary.get("FAILED", 0),
        "running": summary.get("RUNNING", 0),
        "cancelled": summary.get("CANCELLED", 0),
        "queued": summary.get("QUEUED", 0),
        "not_started": 0,  # computed below
    }

    # Datasets with no runs at all
    if batch_def:
        all_ds_ids = {d["dataset_id"] for d in batch_def.get("datasets", [])}
        ds_with_runs = {r.get("OUTPUT_DATASET_ID") for r in rows}
        missing = all_ds_ids - ds_with_runs
        analysis["summary"]["not_started"] = len(missing)
        analysis["summary"]["total_datasets"] = len(all_ds_ids)

    # ---- Per-processing-type breakdown ----
    by_processing_type: dict[str, dict[str, int]] = {}
    for row in rows:
        pt = row.get("processing_type", "UNKNOWN")
        if pt not in by_processing_type:
            by_processing_type[pt] = {"SUCCESS": 0, "FAILED": 0, "RUNNING": 0, "CANCELLED": 0, "QUEUED": 0, "total": 0}
        status = row.get("STATUS", "UNKNOWN")
        by_processing_type[pt]["total"] += 1
        if status in by_processing_type[pt]:
            by_processing_type[pt][status] += 1
    analysis["by_processing_type"] = by_processing_type

    # ---- Sequence progress ----
    if batch_progress and batch_progress.get("steps"):
        steps = batch_progress["steps"]
        overall = batch_progress.get("overall", {})
        analysis["sequence_progress"] = []
        for step in steps:
            analysis["sequence_progress"].append({
                "order": step["sequence_order"],
                "status": step["status"],
                "datasets": step["datasets"],
                "counts": step["counts"],
            })
        analysis["overall_progress"] = {
            "completed": overall.get("completed", 0),
            "total": overall.get("total", 0),
            "fraction": overall.get("fraction", 0.0),
            "display": f"{overall.get('completed', 0)} of {overall.get('total', 0)}",
        }

    # ---- Determine batch-level status ----
    s = analysis["summary"]
    if s["failed"] > 0:
        analysis["batch_status"] = "PARTIAL_FAILURE"
    elif s["running"] > 0:
        analysis["batch_status"] = "RUNNING"
    elif s["success"] == s["total_datasets"] and s["total_datasets"] > 0:
        analysis["batch_status"] = "SUCCESS"
    elif s["success"] == 0 and s["total_datasets"] > 0:
        analysis["batch_status"] = "NOT_STARTED"
    else:
        analysis["batch_status"] = "IN_PROGRESS"

    # ---- Failures detail ----
    failures = []
    for row in rows:
        if row.get("STATUS") == "FAILED":
            created = row.get("CREATED_DATE")
            updated = row.get("UPDATED_DATE")
            duration = _duration_minutes(created, updated)
            failures.append({
                "dataset_id": row.get("OUTPUT_DATASET_ID"),
                "dag_run_id": row.get("DAG_RUN_ID"),
                "status": "FAILED",
                "processing_type": row.get("processing_type", ""),
                "created_date": str(created) if created else None,
                "updated_date": str(updated) if updated else None,
                "duration_minutes": duration,
            })
    analysis["failures"] = failures

    # ---- RCA findings pass-through ----
    if rca_findings:
        analysis["rca"] = rca_findings

    # ---- Duration anomalies ----
    durations = []
    for row in rows:
        if row.get("STATUS") == "SUCCESS":
            dur = _duration_minutes(row.get("CREATED_DATE"), row.get("UPDATED_DATE"))
            if dur is not None:
                durations.append((row.get("OUTPUT_DATASET_ID"), row.get("DAG_RUN_ID"), dur))

    anomalies = _detect_duration_anomalies(durations)
    if anomalies:
        analysis["anomalies"] = anomalies

    # ---- Slice-level analysis ----
    slice_status = query_results.get("slice_status")
    if slice_status and slice_status.get("slices"):
        target_ds = state.get("target_dataset") or {}
        slice_analysis: dict = {
            "dataset_id": target_ds.get("dataset_id") if target_ds else None,
            "slices": [],
            "summary": {"total": 0, "success": 0, "failed": 0, "running": 0, "not_started": 0},
        }
        for pattern, info in slice_status["slices"].items():
            status = info.get("status", "NOT_STARTED")
            slice_analysis["slices"].append({
                "name": pattern,
                "status": status,
                "dag_run_id": info.get("dag_run_id"),
                "created_date": info.get("created_date"),
                "updated_date": info.get("updated_date"),
                "total_runs": info.get("total_runs", 0),
                "duration_minutes": _duration_minutes(
                    info.get("created_date"), info.get("updated_date")
                ),
            })
            slice_analysis["summary"]["total"] += 1
            if status == "SUCCESS":
                slice_analysis["summary"]["success"] += 1
            elif status in ("FAILED", "CANCELLED"):
                slice_analysis["summary"]["failed"] += 1
            elif status in ("RUNNING", "QUEUED"):
                slice_analysis["summary"]["running"] += 1
            else:
                slice_analysis["summary"]["not_started"] += 1
        analysis["slice_analysis"] = slice_analysis

    return {"analysis": analysis}


def _duration_minutes(created, updated) -> int | None:
    """Compute duration in minutes between two timestamps."""
    if not created or not updated:
        return None
    try:
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        delta = (updated - created).total_seconds()
        return max(0, int(delta / 60))
    except (ValueError, TypeError):
        return None


def _detect_duration_anomalies(
    durations: list[tuple[str, str, int]],
) -> list[dict]:
    """Flag runs that took significantly longer than the median."""
    if len(durations) < 3:
        return []

    dur_values = sorted(d[2] for d in durations)
    median = dur_values[len(dur_values) // 2]
    if median == 0:
        return []

    threshold = median * DURATION_ANOMALY_FACTOR
    anomalies = []
    for ds_id, dag_run_id, dur in durations:
        if dur > threshold:
            anomalies.append({
                "dataset_id": ds_id,
                "dag_run_id": dag_run_id,
                "duration_minutes": dur,
                "median_minutes": median,
                "factor": round(dur / median, 1),
            })
    return anomalies
