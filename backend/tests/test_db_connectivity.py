"""
Quick connectivity test for both RDS MySQL databases.

Usage:
    cd backend
    python -m tests.test_db_connectivity
"""

import sys

from sqlalchemy import text

from services.db_service import get_airflow_engine, get_fgw_engine


def test_fgw() -> bool:
    """Test FINEGRAINED_WORKFLOW connectivity."""
    print("--- FINEGRAINED_WORKFLOW ---")
    try:
        engine = get_fgw_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT COUNT(*) FROM WORKFLOW_RUN_INSTANCE "
                    "WHERE business_date = CURDATE()"
                )
            )
            count = result.scalar()
            print(f"  Rows for today: {count}")
            return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


def test_airflow() -> bool:
    """Test airflow connectivity."""
    print("--- airflow ---")
    try:
        engine = get_airflow_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM task_instance LIMIT 1")
            )
            count = result.scalar()
            print(f"  task_instance row count: {count}")
            return True
    except Exception as e:
        print(f"  FAILED: {e}")
        return False


if __name__ == "__main__":
    print("Testing RDS connectivity...\n")
    fgw_ok = test_fgw()
    print()
    airflow_ok = test_airflow()
    print()

    if fgw_ok and airflow_ok:
        print("All connectivity tests PASSED.")
    else:
        print("Some connectivity tests FAILED.")
        sys.exit(1)
