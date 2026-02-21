# Query Tier System

## Overview
SENTRY uses a 3-tier query system to balance reliability, safety, and flexibility.

## Tier 1: Parameterized Tools (80% of queries)

These are pre-built, tested query functions with flexible optional parameters. The LLM's job is parameter extraction, NOT SQL generation.

### Tool Definitions

```python
from typing import Optional, List
from langchain_core.tools import tool

@tool
def get_batch_status(
    dataset_ids: List[str],
    business_date: str,
    processing_type: Optional[str] = None,
    status_filter: Optional[List[str]] = None,
    limit: int = 500
) -> dict:
    """Get workflow status for a batch's datasets from WORKFLOW_RUN_INSTANCE.
    
    Args:
        dataset_ids: List of output_dataset_ids (from Lenz API resolve_batch)
        business_date: Date string YYYY-MM-DD
        processing_type: 'PRELIM', 'FINAL', or None for both
        status_filter: Optional list of statuses to filter ['SUCCESS', 'FAILED', etc.]
        limit: Max rows (default 500)
    
    Returns:
        Dict with 'rows' (list of result dicts) and 'summary' (counts by status)
    """
    trigger_map = {'PRELIM': 'ProcessTrigger', 'FINAL': 'RerunTrigger', 'MANUAL': 'ManualTrigger'}
    
    query = """
        SELECT WORKFLOW_RUN_INSTANCE_KEY, WORKFLOW_ID, DAG_ID, DAG_RUN_ID,
               STATUS, STATUS_DETAIL, TRIGGER_TYPE, CREATED_DATE, UPDATED_DATE,
               OUTPUT_DATASET_ID, BUSINESS_DATE
        FROM FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE
        WHERE business_date = %s
          AND output_dataset_id IN ({placeholders})
    """
    params = [business_date] + dataset_ids
    
    if processing_type and processing_type.upper() in trigger_map:
        query += " AND TRIGGER_TYPE = %s"
        params.append(trigger_map[processing_type.upper()])
    
    if status_filter:
        query += f" AND STATUS IN ({','.join(['%s'] * len(status_filter))})"
        params.extend(status_filter)
    
    query += " ORDER BY CREATED_DATE DESC LIMIT %s"
    params.append(limit)
    # ... execute and return


@tool
def get_task_details(
    dag_run_id: str,
    state_filter: Optional[List[str]] = None
) -> dict:
    """Get task-level details from airflow.task_instance for a specific DAG run.
    
    Args:
        dag_run_id: The DAG_RUN_ID from WORKFLOW_RUN_INSTANCE
        state_filter: Optional list of states ['failed', 'running']
    
    Returns:
        Dict with 'tasks' (list of task dicts ordered by start_date)
    """
    query = """
        SELECT task_id, dag_id, state, duration, start_date, end_date,
               try_number, hostname, operator, task_display_name
        FROM airflow.task_instance
        WHERE run_id = %s
    """
    params = [dag_run_id]
    
    if state_filter:
        query += f" AND state IN ({','.join(['%s'] * len(state_filter))})"
        params.extend(state_filter)
    
    query += " ORDER BY start_date"
    # ... execute and return


@tool
def get_slice_status(
    dataset_id: str,
    business_date: str,
    slice_patterns: List[str],
    processing_type: Optional[str] = None
) -> dict:
    """Get status for specific slices of a dataset by filtering DAG_RUN_ID patterns.
    
    Args:
        dataset_id: Exact output_dataset_id
        business_date: Date string YYYY-MM-DD
        slice_patterns: List of slice name substrings to match in DAG_RUN_ID
        processing_type: 'PRELIM', 'FINAL', or None
    
    Returns:
        Dict with per-slice status
    """
    # Build LIKE conditions for each slice pattern
    # WHERE dag_run_id LIKE '%DERIV-EMEA-SLICE-1%' OR dag_run_id LIKE '%DERIV-EMEA-SLICE-2%'
    # ... implementation


@tool
def get_batch_progress(
    essential_def: dict,
    business_date: str,
    processing_type: Optional[str] = None
) -> dict:
    """Get sequence-aware progress for a batch. Uses Lenz definition to group
    datasets by sequence order and report completion status per step.
    
    Returns:
        Dict with per-sequence-step status, overall progress fraction,
        and ETA estimate if historical data available.
    """
    # 1. Get all dataset_ids from essential_def
    # 2. Query WORKFLOW_RUN_INSTANCE for all
    # 3. Group results by sequence_order
    # 4. For each sequence step, determine: all_success, any_failed, any_running, not_started
    # 5. Return structured progress report


@tool
def get_historical_runs(
    dataset_id: str,
    last_n_business_dates: int = 10,
    processing_type: Optional[str] = None
) -> dict:
    """Get historical run data for trend analysis and runtime prediction.
    
    Returns:
        Dict with per-business-date runtime stats (min, max, avg duration per slice)
    """
    # Query across multiple business_dates
    # Calculate TIMESTAMPDIFF(MINUTE, CREATED_DATE, UPDATED_DATE)
    # Only include STATUS='SUCCESS' for runtime calculations
```

### Tool Invocation Pattern in LangGraph

The LLM sees these tool descriptions and calls them with parameters extracted from the user's question. Example:

User: "How is derivatives PRELIM doing for Feb 13?"
→ Agent calls: `resolve_batch("derivatives")` → gets Lenz definition
→ Agent calls: `get_batch_status(dataset_ids=[...6 IDs from Lenz...], business_date="2026-02-13", processing_type="PRELIM")`
→ Agent calls: `get_batch_progress(essential_def={...}, business_date="2026-02-13", processing_type="PRELIM")`

## Tier 2: Constrained LLM SQL (15% of queries)

For novel analytical questions that Tier 1 can't handle.

### When Tier 2 is triggered
- Cross-batch comparisons ("Which batch had the most failures this week?")
- Novel aggregations ("Average runtime per slice for EMEA vs APAC")
- Ad-hoc time analysis ("Show me all dags that took longer than 2 hours yesterday")
- Historical pattern queries ("Has this specific slice failed before in the last 10 days?")

### Guardrails — ALL MANDATORY
```python
class ConstrainedSQLExecutor:
    ALLOWED_TABLES = [
        "FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE",
        "airflow.task_instance",
        "airflow.dag_run"
    ]
    MAX_ROWS = 500
    QUERY_TIMEOUT_SECONDS = 10
    FORBIDDEN_KEYWORDS = ["DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "GRANT", "TRUNCATE", "CREATE"]
    
    def validate(self, sql: str) -> bool:
        """Validate generated SQL before execution."""
        import sqlparse
        parsed = sqlparse.parse(sql)
        
        # 1. Must be exactly one statement
        if len(parsed) != 1:
            raise SQLValidationError("Only single SELECT statements allowed")
        
        stmt = parsed[0]
        
        # 2. Must be a SELECT
        if stmt.get_type() != 'SELECT':
            raise SQLValidationError(f"Only SELECT allowed, got: {stmt.get_type()}")
        
        # 3. No forbidden keywords
        sql_upper = sql.upper()
        for keyword in self.FORBIDDEN_KEYWORDS:
            if keyword in sql_upper:
                raise SQLValidationError(f"Forbidden keyword: {keyword}")
        
        # 4. Must reference only allowed tables
        # (table extraction from AST)
        
        # 5. Inject LIMIT if not present
        if 'LIMIT' not in sql_upper:
            sql = sql.rstrip(';') + f' LIMIT {self.MAX_ROWS}'
        
        return sql
    
    def execute(self, sql: str) -> dict:
        """Execute with read-only connection and timeout."""
        validated_sql = self.validate(sql)
        # Execute with statement_timeout=10000 (10s)
        # Use read-only connection
```

### Domain Context Injection for Tier 2

Three layers combined into the LLM prompt:

1. **Auto-discovered schema**: From `langchain_community.utilities.SQLDatabase.get_table_info()` — refreshed at startup
2. **Static domain rules**: TRIGGER_TYPE mappings, DAG_RUN_ID format, mandatory filters
3. **Dynamic few-shot examples**: Retrieved from vector store based on query similarity

```python
# SQL examples stored in sql_examples.json and loaded into vector store
SQL_EXAMPLES = [
    {
        "question": "DERIVATIVES PRELIM status for a business date",
        "sql": "SELECT output_dataset_id, dag_run_id, STATUS, TRIGGER_TYPE, CREATED_DATE, UPDATED_DATE FROM FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE WHERE business_date = '2026-02-13' AND output_dataset_id IN ('com.jpmc.ct.lri.derivatives-pb_synthetics_trs_e15', 'com.jpmc.ct.lri.derivatives-slsline_calculator_e15', ...) AND TRIGGER_TYPE = 'ProcessTrigger' ORDER BY CREATED_DATE DESC LIMIT 500"
    },
    {
        "question": "How long did each slice take for a specific dataset FINAL run",
        "sql": "SELECT dag_run_id, TIMESTAMPDIFF(MINUTE, CREATED_DATE, UPDATED_DATE) as duration_minutes, STATUS FROM FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE WHERE business_date = '2026-02-13' AND output_dataset_id = 'com.jpmc.ct.lri.derivatives-slsline_calculator_e15' AND TRIGGER_TYPE = 'RerunTrigger' ORDER BY duration_minutes DESC LIMIT 500"
    },
    {
        "question": "Which tasks failed in a specific dag run",
        "sql": "SELECT task_id, state, duration, start_date, end_date, try_number FROM airflow.task_instance WHERE run_id = 'FGW_...' AND state = 'failed' ORDER BY start_date LIMIT 500"
    }
]
```

### CRITICAL: Batch→Dataset resolution BEFORE Tier 2

Even in Tier 2, the Lenz API must be called first. The resolved dataset IDs are injected as FACT into the SQL generation prompt:

```
BATCH CONTEXT:
The user is asking about "SNU" batch.
This batch contains these EXACT output_dataset_ids — use IN (...) operator:
["com.jpmc.ct.lri.upc.global-upc_allocation_result_strategic",
 "com.jpmc.ct.lri.derivatives.global-pb_synthetics_orig_src_data",
 "com.jpmc.ct.lri.snu_acc_calc_adapter_result_strategic",
 ... 22 total IDs ...]

Do NOT use LIKE patterns for batch filtering.
```

## Tier 3: Graceful Decline (5% of queries)

Questions outside SENTRY's scope:
- "Why did the business decide to rerun EMEA?" → Business decision, not in DB
- "Can you restart that DAG?" → SENTRY is read-only, no write actions
- "What's the weather like?" → Completely off-topic

Response pattern: Acknowledge the question, explain why it's outside scope, suggest what SENTRY can help with instead.
