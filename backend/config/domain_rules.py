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

# ---------------------------------------------------------------------------
# Domain glossary — injected into every LLM node system prompt
# ---------------------------------------------------------------------------
DOMAIN_GLOSSARY = """\
DOMAIN TERMINOLOGY — JPMorgan Chase Batch Processing:

ESSENTIAL (also called "Batch" or "Asset Class"):
  A monitored group of datasets representing a complete business workflow.
  Examples: DERIVATIVES, SECURITIES, SNU, FR2052A (6G), COLLATERAL, UPC.
  An Essential is an ARBITRARY grouping — dataset names do NOT follow naming
  patterns of their parent Essential. Always resolve via Lenz API.

DATASET:
  A single data pipeline within an Essential. Identified by a globally unique ID
  (e.g., com.jpmc.ct.lri.derivatives-slsline_calculator_e15). Each dataset runs
  as an Airflow DAG. A dataset belongs to exactly one Essential (as defined by Lenz).

SLICE:
  A parallel execution unit within a dataset. When a dataset processes data across
  multiple regions or segments, each segment runs as a separate slice.
  Example slices for the intercompany dataset: AWS_OTC_DERIV_AGG_EMEA,
  AWS_CRI_OTC_DERIV_GLOBAL, AWS_DERIV_PB_SYNTHETIC_EMEA.
  Not all datasets have slices — some run as a single unit.
  Slice names are defined in Lenz API under each dataset's sliceGroups field.

SEQUENCE ORDER:
  Datasets within an Essential execute in a defined order (0 → 1 → 2 → ...).
  Datasets with the SAME sequence number run in parallel.
  Higher-sequence datasets wait for all lower-sequence datasets to complete.
  This is critical for progress reporting ("step 3 of 6") and identifying blockers.

PRELIM / FINAL:
  Each dataset can run up to twice per business day:
  - PRELIM: First run of the day. Triggered by ProcessTrigger.
  - FINAL: Second run (reprocessing). Triggered by RerunTrigger.
  - MANUAL: Ad-hoc retry after failure. Triggered by ManualTrigger.
  The database column TRIGGER_TYPE stores the trigger class name, not PRELIM/FINAL.

BUSINESS DATE:
  The date for which batch data is being processed. This is NOT necessarily today's
  calendar date — batches can process data for previous business dates.
  Every database query MUST filter on business_date.

DAG_RUN_ID:
  Unique execution identifier for a single slice of a dataset.
  Format: FGW_{dag_id}_{business_date}_{slice_name}_{unique_integer}
  Example: FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-NA-SLICE-2_1771101266610

STATUS VALUES:
  Workflow level: SUCCESS, FAILED, CANCELLED, RUNNING, QUEUED
  Task level (Airflow): success, failed, running, queued, upstream_failed, skipped
  Essential aggregate: SUCCESS, PARTIAL_FAILURE, FAILED, RUNNING, NOT_STARTED, WAITING\
"""
