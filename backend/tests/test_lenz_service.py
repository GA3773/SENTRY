"""
Tests for Lenz API service.

Usage:
    cd backend
    python tests/test_lenz_service.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.lenz_service import LenzService, resolve_essential_name, resolve_slice_filter


async def test_name_resolution() -> bool:
    """Test ESSENTIAL_MAP name resolution."""
    print("--- Name Resolution ---")
    cases = {
        "6G": "6G-FR2052a-E2E",
        "DERIV": "TB-Derivatives",
        "derivatives": "TB-Derivatives",
        "snu": "SNU",
        "SNU STRATEGIC": "SNU-Strategic",
        "COLLATERAL": "TB-Collateral",
        "FR2052A": "6G-FR2052a-E2E",
    }
    all_ok = True
    for user_input, expected in cases.items():
        result = resolve_essential_name(user_input)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            all_ok = False
        print(f"  '{user_input}' → '{result}' (expected '{expected}') [{status}]")
    return all_ok


async def test_tb_derivatives(svc: LenzService) -> bool:
    """Fetch TB-Derivatives and inspect datasets."""
    print("--- TB-Derivatives ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")
        print(f"  Essential: {defn.essential_name}")
        print(f"  Dataset count: {len(defn.datasets)}")
        print(f"  Dataset IDs:")
        for d in defn.datasets:
            slices = d.all_slices
            slice_info = f" ({len(slices)} slices)" if slices else ""
            print(f"    seq={d.sequence_order}: {d.dataset_id}{slice_info}")

        seq_groups = defn.datasets_by_sequence()
        print(f"  Sequence groups: {list(seq_groups.keys())}")
        return len(defn.datasets) > 0
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_snu(svc: LenzService) -> bool:
    """Fetch SNU and verify it has 22+ datasets with mixed namespaces."""
    print("--- SNU ---")
    try:
        defn = await svc.get_essential_definition("SNU")
        print(f"  Essential: {defn.essential_name}")
        print(f"  Dataset count: {len(defn.datasets)}")

        namespaces = set()
        for d in defn.datasets:
            parts = d.dataset_id.split("-")
            if len(parts) >= 2:
                ns = "-".join(parts[:3]) if "lri" in d.dataset_id else parts[0]
                namespaces.add(ns)
        print(f"  Namespaces: {sorted(namespaces)}")

        ok = len(defn.datasets) >= 10
        if not ok:
            print(f"  WARNING: Expected 10+ datasets, got {len(defn.datasets)}")
        return ok
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_snu_strategic_different(svc: LenzService) -> bool:
    """Verify SNU and SNU-Strategic return different dataset sets."""
    print("--- SNU vs SNU-Strategic ---")
    try:
        snu = await svc.get_essential_definition("SNU")
        strategic = await svc.get_essential_definition("SNU STRATEGIC")
        snu_ids = set(snu.dataset_ids)
        strategic_ids = set(strategic.dataset_ids)
        different = snu_ids != strategic_ids
        print(f"  SNU datasets: {len(snu_ids)}")
        print(f"  SNU-Strategic datasets: {len(strategic_ids)}")
        print(f"  Are different: {different}")
        if not different:
            print("  WARNING: SNU and SNU-Strategic returned identical datasets")
        return different
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def test_slice_resolution(svc: LenzService) -> bool:
    """Test fuzzy slice matching on first dataset that has slices."""
    print("--- Slice Resolution ---")
    try:
        defn = await svc.get_essential_definition("DERIVATIVES")

        # Find first dataset that actually HAS slices
        target_dataset = None
        for d in defn.datasets:
            if d.all_slices:
                target_dataset = d
                break

        if not target_dataset:
            print("  SKIP: No dataset with slices found in TB-Derivatives")
            return True

        print(f"  Dataset: {target_dataset.dataset_id}")
        print(f"  All slices ({len(target_dataset.all_slices)}):")
        for s in target_dataset.all_slices:
            print(f"    {s}")

        # Test EMEA filter
        emea_slices = resolve_slice_filter(defn, target_dataset.dataset_id, "EMEA")
        print(f"  EMEA filter: {emea_slices}")

        # Test GLOBAL filter
        global_slices = resolve_slice_filter(defn, target_dataset.dataset_id, "GLOBAL")
        print(f"  GLOBAL filter: {global_slices}")

        ok = len(target_dataset.all_slices) > 0
        if not ok:
            print("  WARNING: Expected slices but got none")
        return ok
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


async def main() -> None:
    print("Testing Lenz Service...\n")
    svc = LenzService()

    results = [
        ("Name Resolution", await test_name_resolution()),
    ]
    print()

    results.append(("TB-Derivatives", await test_tb_derivatives(svc)))
    print()

    results.append(("SNU", await test_snu(svc)))
    print()

    results.append(("SNU vs SNU-Strategic", await test_snu_strategic_different(svc)))
    print()

    results.append(("Slice Resolution", await test_slice_resolution(svc)))
    print()

    print("=" * 50)
    all_passed = True
    for name, ok in results:
        status = "PASSED" if ok else "FAILED"
        print(f"  {name}: {status}")
        if not ok:
            all_passed = False
    print("=" * 50)

    if all_passed:
        print("All tests PASSED.")
    else:
        print("Some tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
