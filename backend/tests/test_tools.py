"""
Tests for Tier 1 parameterized query tools.

Tests run against the live RDS database. Requires .env with valid credentials.

Usage:
    cd backend
    python tests/test_tools.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.domain_rules import (
    DEFAULT_QUERY_LIMIT,
    TRIGGER_TYPE_MAP,
    TRIGGER_TYPE_REVERSE,
)
from services.lenz_service import LenzService

from agent.tools.batch_tools import (
    get_batch_status,
    get_batch_progress,
    get_slice_status,
    get_historical_runs,
)
from agent.tools.task_tools import get_task_details


# Use a recent business date for live testing
TEST_BUSINESS_DATE = "2026-02-13"


async def test_trigger_type_mapping() -> bool:
    """Verify TRIGGER_TYPE mapping is correct and bidirectional."""
    print("--- TRIGGER_TYPE Mapping ---")
    expected = {
        "PRELIM": "ProcessTrigger",
        "FINAL": "RerunTrigger",
        "MANUAL": "ManualTrigger",
    }
    ok = True
    for human, db_val in expected.items():
        fwd = TRIGGER_TYPE_MAP.get(human)
        rev = TRIGGER_TYPE_REVERSE.get(db_val)
        fwd_ok = fwd == db_val
        rev_ok = rev == human
        if not fwd_ok or not rev_ok:
            ok = False
        print(f"  {human} → {fwd} (exp {db_val}) [{fwd_ok}], reverse: {rev} [{rev_ok}]")
    return ok


async def test_batch_status_derivatives(svc: LenzService) -> bool:
    """Test get_batch_status for TB-Derivatives on a recent business date."""
    print(f"--- get_batch_status (DERIVATIVES, {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        dataset_ids = defn.dataset_ids
        print(f"  Resolved {len(dataset_ids)} dataset IDs from Lenz")

        result = get_batch_status(
            dataset_ids=dataset_ids,
            business_date=TEST_BUSINESS_DATE,
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Total rows: {result['total']}")
        print(f"  Summary: {result['summary']}")

        # Verify LIMIT is respected
        if result["total"] > DEFAULT_QUERY_LIMIT:
            print(f"  FAIL: Got {result['total']} rows, exceeds limit {DEFAULT_QUERY_LIMIT}")
            return False

        # Verify each row has the expected columns
        if result["rows"]:
            row = result["rows"][0]
            required = [
                "WORKFLOW_ID", "DAG_ID", "DAG_RUN_ID", "STATUS",
                "TRIGGER_TYPE", "OUTPUT_DATASET_ID", "BUSINESS_DATE",
                "processing_type",
            ]
            missing = [c for c in required if c not in row]
            if missing:
                print(f"  FAIL: Missing columns: {missing}")
                return False
            print(f"  Sample row dataset: {row['OUTPUT_DATASET_ID']}")
            print(f"  Sample row status: {row['STATUS']} ({row['processing_type']})")

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_batch_status_with_processing_type(svc: LenzService) -> bool:
    """Test get_batch_status with PRELIM filter."""
    print(f"--- get_batch_status (DERIVATIVES, PRELIM, {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        dataset_ids = defn.dataset_ids

        result = get_batch_status(
            dataset_ids=dataset_ids,
            business_date=TEST_BUSINESS_DATE,
            processing_type="PRELIM",
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  PRELIM rows: {result['total']}")
        print(f"  Summary: {result['summary']}")

        # Verify all rows are ProcessTrigger
        for row in result["rows"]:
            if row["TRIGGER_TYPE"] != "ProcessTrigger":
                print(f"  FAIL: Got TRIGGER_TYPE={row['TRIGGER_TYPE']}, expected ProcessTrigger")
                return False

        if result["rows"]:
            print("  All rows have correct TRIGGER_TYPE=ProcessTrigger")

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_batch_status_with_status_filter(svc: LenzService) -> bool:
    """Test get_batch_status with status filter."""
    print(f"--- get_batch_status (DERIVATIVES, status=FAILED, {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        dataset_ids = defn.dataset_ids

        result = get_batch_status(
            dataset_ids=dataset_ids,
            business_date=TEST_BUSINESS_DATE,
            status_filter=["FAILED"],
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  FAILED rows: {result['total']}")

        for row in result["rows"]:
            if row["STATUS"] != "FAILED":
                print(f"  FAIL: Got STATUS={row['STATUS']}, expected FAILED")
                return False

        if result["rows"]:
            print("  All rows have STATUS=FAILED")
        else:
            print("  No FAILED runs found (this is OK)")

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_batch_status_empty_datasets() -> bool:
    """Test get_batch_status with empty dataset list returns cleanly."""
    print("--- get_batch_status (empty datasets) ---")
    result = get_batch_status(dataset_ids=[], business_date=TEST_BUSINESS_DATE)
    ok = result["rows"] == [] and result["total"] == 0
    print(f"  Empty input returns empty result: {ok}")
    return ok


async def test_batch_progress(svc: LenzService) -> bool:
    """Test get_batch_progress for sequence-aware progress tracking."""
    print(f"--- get_batch_progress (DERIVATIVES, {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        essential_dict = defn.model_dump()

        result = get_batch_progress(
            essential_def=essential_dict,
            business_date=TEST_BUSINESS_DATE,
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Steps: {len(result['steps'])}")
        for step in result["steps"]:
            print(
                f"    Seq {step['sequence_order']}: {step['status']} "
                f"({step['counts']['success']}/{step['counts']['total']} success, "
                f"{len(step['datasets'])} datasets)"
            )

        overall = result["overall"]
        print(
            f"  Overall: {overall['completed']}/{overall['total']} "
            f"({overall['fraction']:.1%})"
        )

        # Verify structure
        if not result["steps"]:
            print("  WARNING: No steps returned (might be OK if no data for this date)")
        if overall["total"] != len(defn.datasets):
            print(
                f"  FAIL: Total {overall['total']} != dataset count {len(defn.datasets)}"
            )
            return False

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_slice_status(svc: LenzService) -> bool:
    """Test get_slice_status with known slice patterns from Lenz."""
    print(f"--- get_slice_status (DERIVATIVES, {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")

        # Find a dataset with slices
        target = None
        for d in defn.datasets:
            if d.all_slices:
                target = d
                break

        if not target:
            print("  SKIP: No dataset with slices found")
            return True

        slices = target.all_slices[:3]  # Test with first 3 slices
        print(f"  Dataset: {target.dataset_id}")
        print(f"  Testing slices: {slices}")

        result = get_slice_status(
            dataset_id=target.dataset_id,
            business_date=TEST_BUSINESS_DATE,
            slice_patterns=slices,
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Total matching rows: {result['total']}")
        for pattern, info in result["slices"].items():
            print(f"    {pattern}: {info.get('status', 'N/A')} (runs: {info.get('total_runs', 0)})")

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_task_details(svc: LenzService) -> bool:
    """Test get_task_details by first finding a DAG_RUN_ID from batch status."""
    print(f"--- get_task_details ({TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        dataset_ids = defn.dataset_ids

        # Get a DAG_RUN_ID from batch status
        batch_result = get_batch_status(
            dataset_ids=dataset_ids,
            business_date=TEST_BUSINESS_DATE,
        )

        if not batch_result["rows"]:
            print("  SKIP: No batch rows found to get a DAG_RUN_ID")
            return True

        dag_run_id = batch_result["rows"][0]["DAG_RUN_ID"]
        print(f"  Using DAG_RUN_ID: {dag_run_id}")

        result = get_task_details(dag_run_id=dag_run_id)

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Tasks found: {result['total']}")
        print(f"  State summary: {result['summary']}")

        if result["tasks"]:
            for task in result["tasks"][:5]:
                dur = task.get("duration")
                dur_str = f"{dur:.1f}s" if dur else "N/A"
                print(
                    f"    {task['task_id'][:60]}: {task['state']} ({dur_str})"
                )
            if result["total"] > 5:
                print(f"    ... and {result['total'] - 5} more tasks")

        # Verify LIMIT is respected
        if result["total"] > DEFAULT_QUERY_LIMIT:
            print(f"  FAIL: Got {result['total']} tasks, exceeds limit {DEFAULT_QUERY_LIMIT}")
            return False

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_task_details_with_state_filter(svc: LenzService) -> bool:
    """Test get_task_details with a state filter."""
    print(f"--- get_task_details (state_filter=['failed'], {TEST_BUSINESS_DATE}) ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        dataset_ids = defn.dataset_ids

        batch_result = get_batch_status(
            dataset_ids=dataset_ids,
            business_date=TEST_BUSINESS_DATE,
            status_filter=["FAILED"],
        )

        if not batch_result["rows"]:
            print("  SKIP: No FAILED batch rows found")
            return True

        dag_run_id = batch_result["rows"][0]["DAG_RUN_ID"]
        print(f"  Using FAILED DAG_RUN_ID: {dag_run_id}")

        result = get_task_details(
            dag_run_id=dag_run_id,
            state_filter=["failed"],
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Failed tasks: {result['total']}")
        for task in result["tasks"]:
            print(f"    {task['task_id'][:60]}: try #{task.get('try_number', '?')}")

        # Verify all returned tasks are 'failed'
        for task in result["tasks"]:
            if task["state"] != "failed":
                print(f"  FAIL: Got state={task['state']}, expected 'failed'")
                return False

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_task_details_empty_run_id() -> bool:
    """Test get_task_details with empty run_id returns cleanly."""
    print("--- get_task_details (empty run_id) ---")
    result = get_task_details(dag_run_id="")
    ok = result["tasks"] == [] and result["total"] == 0
    print(f"  Empty input returns empty result: {ok}")
    return ok


async def test_historical_runs(svc: LenzService) -> bool:
    """Test get_historical_runs for a known dataset."""
    print("--- get_historical_runs ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        if not defn.datasets:
            print("  SKIP: No datasets")
            return True

        dataset_id = defn.datasets[0].dataset_id
        print(f"  Dataset: {dataset_id}")

        result = get_historical_runs(
            dataset_id=dataset_id,
            last_n_business_dates=5,
            processing_type="PRELIM",
        )

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return False

        print(f"  Business dates found: {len(result['history'])}")
        for entry in result["history"]:
            print(
                f"    {entry['business_date']}: "
                f"{entry['run_count']} runs, "
                f"avg {entry['avg_minutes']}min "
                f"(range {entry['min_minutes']}-{entry['max_minutes']}min)"
            )

        if result["stats"]:
            s = result["stats"]
            print(
                f"  Stats: P50={s['p50_minutes']}min, "
                f"P90={s['p90_minutes']}min, "
                f"P95={s['p95_minutes']}min "
                f"(n={s['sample_count']})"
            )

        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def main() -> None:
    print("Testing Tier 1 Tools...\n")
    svc = LenzService()

    results: list[tuple[str, bool]] = []

    results.append(("TRIGGER_TYPE Mapping", await test_trigger_type_mapping()))
    print()

    results.append(("Batch Status (empty)", await test_batch_status_empty_datasets()))
    print()

    results.append(("Task Details (empty)", await test_task_details_empty_run_id()))
    print()

    results.append(("Batch Status (DERIV)", await test_batch_status_derivatives(svc)))
    print()

    results.append(("Batch Status (PRELIM)", await test_batch_status_with_processing_type(svc)))
    print()

    results.append(("Batch Status (FAILED)", await test_batch_status_with_status_filter(svc)))
    print()

    results.append(("Batch Progress", await test_batch_progress(svc)))
    print()

    results.append(("Slice Status", await test_slice_status(svc)))
    print()

    results.append(("Task Details", await test_task_details(svc)))
    print()

    results.append(("Task Details (filter)", await test_task_details_with_state_filter(svc)))
    print()

    results.append(("Historical Runs", await test_historical_runs(svc)))
    print()

    print("=" * 60)
    all_passed = True
    for name, ok in results:
        status = "PASSED" if ok else "FAILED"
        print(f"  {name}: {status}")
        if not ok:
            all_passed = False
    print("=" * 60)

    if all_passed:
        print("All tests PASSED.")
    else:
        print("Some tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
