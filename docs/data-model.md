# SENTRY Data Model & Database Schemas

## Database Connections

Two MySQL databases on RDS Aurora, accessed via the same RDS instance:

1. **FINEGRAINED_WORKFLOW** — Business database with batch/workflow status
2. **airflow** — Airflow metadata database with DAG and task details

Connection details: See @docs/connectivity.md
RDS connectivity pattern: https://raw.githubusercontent.com/GA3773/Comm/refs/heads/main/backend/db.py

## Table: FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE

This is the PRIMARY table for batch monitoring. Each row represents one execution of one workflow (DAG) for one slice.

### Schema
```sql
CREATE TABLE WORKFLOW_RUN_INSTANCE (
    WORKFLOW_RUN_INSTANCE_KEY  INT           NOT NULL AUTO_INCREMENT PRIMARY KEY,
    WORKFLOW_KEY               INT           NOT NULL,
    WORKFLOW_ID                VARCHAR(256)  NOT NULL,
    DAG_ID                     VARCHAR(256),
    DAG_RUN_ID                 VARCHAR(256),
    STATUS                     VARCHAR(256),
    STATUS_DETAIL              VARCHAR(1024),
    CREATED_DATE               TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UPDATED_DATE               TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    BUSINESS_DATE              DATE,
    MODEL_BUSINESS_DATE        DATE,
    MODEL_AS_OF_DATE           DATE,
    OUTPUT_DATASET_ID          VARCHAR(256),
    DATA_PROCESSOR_ID          VARCHAR(256),
    OUTPUT_BUSINESS_DATE_RULE  VARCHAR(256),
    TRIGGER_TYPE               VARCHAR(256),
    TRIGGER_VALUE              VARCHAR(256),
    OUTPUT_DATASET_EFFECTIVE_DATE DATETIME,
    OUTPUT_DATASET_AS_OF_DATE    DATETIME
);
-- Indexes on: BUSINESS_DATE, OUTPUT_DATASET_ID
```

### Column Semantics (CRITICAL — read before writing any query)

| Column | Meaning | Notes |
|--------|---------|-------|
| BUSINESS_DATE | The date for which the batch was processed | ALWAYS filter on this. It's indexed. |
| OUTPUT_DATASET_ID | Unique ID for the dataset being processed | Maps to Lenz API `datasetId`. This is how you join to batch definitions. |
| WORKFLOW_ID | String subset of OUTPUT_DATASET_ID | The workflow name |
| DAG_ID | Airflow DAG identifier | Usually WORKFLOW_ID + version suffix (e.g., `_V2`) |
| DAG_RUN_ID | Unique execution identifier | Format: `FGW_{DAG_ID}_{BUSINESS_DATE}_{SLICE_NAME}_{UNIQUE_INT}` |
| STATUS | Execution status | Values: `SUCCESS`, `FAILED`, `CANCELLED`, `RUNNING`, `QUEUED` |
| STATUS_DETAIL | Human-readable status message | Contains DAG name, run ID, and completion status |
| CREATED_DATE | When this run was created/started | Use as `start_time` |
| UPDATED_DATE | When status was last updated | For SUCCESS/FAILED/CANCELLED: this is `end_time`. For RUNNING: this is last heartbeat. |
| TRIGGER_TYPE | How the run was initiated | `ProcessTrigger`=PRELIM, `RerunTrigger`=FINAL, `ManualTrigger`=MANUAL |
| TRIGGER_VALUE | Additional trigger context | Values like `ALL_DATA\|ALL_NEW_MARKER\|EACH_USER` or `NONE_DATA\|ALL_NEW_MARKER\|EACH_USER` |

### DAG_RUN_ID Format — CRITICAL
```
FGW_{dag_id}_{business_date}_{slice_name}_{unique_integer}

Examples:
FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-NA-SLICE-2_1771101266610
FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-EMEA-SLICE-1_1771105744082
FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
```

To extract slice name: everything between the business_date and the final integer.
Slice patterns vary by dataset — ALWAYS check Lenz API for valid slices.

### TRIGGER_TYPE Mapping — ABSOLUTE RULE
```
ProcessTrigger  → PRELIM processing (first run of the day)
RerunTrigger    → FINAL processing (second run of the day)
ManualTrigger   → Manual intervention by SRE (after failures)
```

### Multiple Runs Per Slice
For a given (OUTPUT_DATASET_ID + BUSINESS_DATE + slice), there can be MULTIPLE rows:
- Original PRELIM run (ProcessTrigger)
- Cancelled run (STATUS=CANCELLED)
- Manual retry (ManualTrigger)
- FINAL rerun (RerunTrigger)

**IMPORTANT: Slice names are known from Lenz API** — each dataset's `sliceGroups` contains the exact valid slice names. Do NOT try to extract slice names by parsing DAG_RUN_ID with substring operations. Instead:

1. Get valid slices for a dataset from Lenz API (see @docs/lenz-integration.md)
2. Match slices to DAG_RUN_IDs using `dag_run_id LIKE '%{slice_name}%'`
3. For "latest run" per known slice, use:

```sql
SELECT * FROM (
    SELECT *,
        ROW_NUMBER() OVER(
            PARTITION BY OUTPUT_DATASET_ID
            ORDER BY CREATED_DATE DESC
        ) as rn
    FROM WORKFLOW_RUN_INSTANCE
    WHERE business_date = %s
      AND output_dataset_id IN (%s)
      AND dag_run_id LIKE %s  -- e.g., '%DERIV-NA-SLICE-2%'
) ranked WHERE rn = 1
```

For getting the latest run per dataset (across all slices):
```sql
SELECT * FROM (
    SELECT *,
        ROW_NUMBER() OVER(
            PARTITION BY OUTPUT_DATASET_ID, TRIGGER_TYPE
            ORDER BY CREATED_DATE DESC
        ) as rn
    FROM WORKFLOW_RUN_INSTANCE
    WHERE business_date = %s AND output_dataset_id IN (%s)
) ranked WHERE rn = 1
```

### Sample Data
```
WORKFLOW_RUN_INSTANCE_KEY | WORKFLOW_ID              | DAG_ID                      | DAG_RUN_ID                                                                    | STATUS    | TRIGGER_TYPE   | BUSINESS_DATE | CREATED_DATE     | UPDATED_DATE
2538431                  | slsline_calculator_e15   | slsline_calculator_e15_V2   | FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-NA-SLICE-1_1771103209811       | SUCCESS   | ManualTrigger  | 2026-02-13    | 2/13/2026 16:59  | 2/14/2026 21:20
2544084                  | slsline_calculator_e15   | slsline_calculator_e15_V2   | FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-EMEA-TRIGGER_1771224970972     | SUCCESS   | RerunTrigger   | 2026-02-13    | 2/16/2026 6:55   | 2/16/2026 7:11
2538298                  | slsline_calculator_e15   | slsline_calculator_e15_V2   | FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-EMEA-SLICE-2_1771000676695     | CANCELLED | ProcessTrigger | 2026-02-13    | 2/13/2026 16:37  | 2/13/2026 17:03
```

## Table: airflow.task_instance

Details of each task within a DAG execution. This is where you drill down from "DAG failed" to "which specific task failed."

### Key Columns
| Column | Meaning | Notes |
|--------|---------|-------|
| task_id | Name of the task | e.g., `start`, `enrich_com.jpmc.ct.lri.intercompany-intercompany_results`, `end` |
| dag_id | Which DAG this task belongs to | Same as DAG_ID in WORKFLOW_RUN_INSTANCE |
| run_id | **Joins to DAG_RUN_ID** from WORKFLOW_RUN_INSTANCE | THIS IS THE CRITICAL JOIN KEY |
| start_date | When the task started executing | |
| end_date | When the task finished | |
| duration | Execution time in seconds | |
| state | Task status | Values: `success`, `failed`, `running`, `queued`, `upstream_failed`, `skipped` |
| try_number | How many times the task was attempted | |
| hostname | Kubernetes pod that ran the task | |
| operator | Airflow operator type | e.g., `EpsInitOperator`, `EpsEnrichmentOperator`, `EpsEgressOperator` |

### Sample Data
```
task_id                                                       | dag_id                    | state   | duration  | start_date | end_date   | run_id
start                                                         | intercompany_workflow_V2  | success | 1.003     | 05:50.6    | 05:51.6    | FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
enrich_com.jpmc.ct.lri.intercompany-intercompany_results      | intercompany_workflow_V2  | success | 184.473   | 05:57.4    | 09:01.9    | FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
egress_com.jpmc.ct.lri.intercompany-intercompany_results      | intercompany_workflow_V2  | success | 242.59    | 09:06.8    | 13:09.4    | FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
snowflake-export-com.jpmc.ct.lri.intercompany-intercompany... | intercompany_workflow_V2  | success | 32.534    | 09:08.1    | 09:40.7    | FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
end                                                           | intercompany_workflow_V2  | success | 0.975     | 13:15.2    | 13:16.2    | FGW_intercompany_workflow_V2_2026-02-12_AWS_OTC_DERIV_AGG_GLOBAL_1770973543050
```

### Typical Task Sequence in a DAG
1. `start` (EpsInitOperator) — initialization
2. `enrich_*` (EpsEnrichmentOperator) — data enrichment/processing (usually longest)
3. `egress_*` (EpsEgressOperator) — data export (often runs parallel with snowflake-export)
4. `snowflake-export-*` (EpsPostTaskOperator) — export to Snowflake
5. `end` (EpsWorkflowCompleteOperator) — completion marker

## Cross-Database Query Pattern

To get task-level details for a batch's DAG execution:
```sql
-- Step 1: Get DAG_RUN_IDs from FINEGRAINED_WORKFLOW
SELECT DAG_RUN_ID, STATUS, OUTPUT_DATASET_ID, CREATED_DATE, UPDATED_DATE
FROM FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE
WHERE business_date = '2026-02-13'
  AND output_dataset_id IN ('dataset1', 'dataset2', ...)
  AND TRIGGER_TYPE = 'ProcessTrigger'  -- for PRELIM
ORDER BY CREATED_DATE DESC;

-- Step 2: Use the DAG_RUN_ID to query task details
SELECT task_id, state, duration, start_date, end_date, try_number, operator
FROM airflow.task_instance
WHERE run_id = 'FGW_slsline_calculator_e15_V2_2026-02-13_DERIV-NA-SLICE-1_1771103209811'
ORDER BY start_date;
```

These are TWO SEPARATE QUERIES (different databases). The agent must execute step 1, extract DAG_RUN_IDs from results, then execute step 2 with those IDs.

## Duration Calculation
```sql
TIMESTAMPDIFF(MINUTE, CREATED_DATE, UPDATED_DATE) AS duration_minutes
```
Only valid when STATUS IN ('SUCCESS', 'FAILED', 'CANCELLED'). For RUNNING status, duration = TIMESTAMPDIFF(MINUTE, CREATED_DATE, NOW()).
