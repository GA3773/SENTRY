from __future__ import annotations

"""
Static domain rules for SENTRY query system.

These mappings are ABSOLUTE — they never change and are derived from
the WORKFLOW_RUN_INSTANCE schema and JPMC batch processing conventions.
"""

# ---------------------------------------------------------------------------
# TRIGGER_TYPE → processing type mapping (ABSOLUTE RULE)
# ---------------------------------------------------------------------------
# ProcessTrigger  → PRELIM processing (first run of the day)
# RerunTrigger    → FINAL processing (second run of the day)
# ManualTrigger   → Manual intervention by SRE (after failures)

TRIGGER_TYPE_MAP: dict[str, str] = {
    "PRELIM": "ProcessTrigger",
    "FINAL": "RerunTrigger",
    "MANUAL": "ManualTrigger",
}

TRIGGER_TYPE_REVERSE: dict[str, str] = {v: k for k, v in TRIGGER_TYPE_MAP.items()}

# ---------------------------------------------------------------------------
# DAG_RUN_ID format
# ---------------------------------------------------------------------------
# Format: FGW_{dag_id}_{business_date}_{slice_name}_{unique_integer}
#
# Examples:
#   FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-NA-SLICE-2_1771101266610
#   FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
#
# IMPORTANT: Do NOT parse slice names from DAG_RUN_ID with substring operations.
# Always get valid slices from the Lenz API, then match with LIKE '%{slice}%'.

# ---------------------------------------------------------------------------
# Workflow status values
# ---------------------------------------------------------------------------
VALID_STATUSES = ["SUCCESS", "FAILED", "CANCELLED", "RUNNING", "QUEUED"]

# Airflow task states (lowercase in the DB)
VALID_TASK_STATES = [
    "success", "failed", "running", "queued",
    "upstream_failed", "skipped",
]

# ---------------------------------------------------------------------------
# Query safety limits
# ---------------------------------------------------------------------------
DEFAULT_QUERY_LIMIT = 500
QUERY_TIMEOUT_SECONDS = 10
