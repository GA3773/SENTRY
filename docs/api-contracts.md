# SENTRY API Contracts

All endpoints are served by FastAPI on port 8000. Frontend (Vite, port 5173) proxies `/api` requests to backend.

## POST /api/chat

Main conversational endpoint. Accepts user message, runs LangGraph agent, returns response.

**Request:**
```json
{
    "message": "How is derivatives doing today?",
    "thread_id": "uuid-string",
    "business_date": "2026-02-21",
    "processing_type": "PRELIM"
}
```
- `message` (required): User's natural language query
- `thread_id` (required): UUID identifying the conversation session. Same thread_id = continued conversation with memory. New UUID = fresh conversation.
- `business_date` (optional): Override default date (today). Frontend sends this from the date picker.
- `processing_type` (optional): "PRELIM", "FINAL", or null for both. Frontend sends this from the toggle.

**Response:**
```json
{
    "thread_id": "uuid-string",
    "response": {
        "text": "DERIVATIVES PRELIM for Feb 21 is partially complete. 4 of 6 sequence steps finished. Step 4 (CFG) has 2 failed slices...",
        "structured_data": {
            "type": "batch_status",
            "batch_name": "TB-Derivatives",
            "business_date": "2026-02-21",
            "processing_type": "PRELIM",
            "summary": {
                "total_datasets": 6,
                "success": 3,
                "failed": 1,
                "running": 1,
                "not_started": 1
            },
            "sequence_progress": [
                {"order": 0, "status": "success", "datasets": ["com.jpmc.ct.lri.derivatives-pb_synthetics_trs_e15", "com.jpmc.ct.lri.derivatives-slsline_calculator_e15"]},
                {"order": 1, "status": "success", "datasets": ["com.jpmc.ct.lri.derivatives-calc_intercompany_fx_adjustment_e15"]},
                {"order": 2, "status": "success", "datasets": ["com.jpmc.ct.lri.derivatives-calc_secured_vs_unsecured_e15"]},
                {"order": 3, "status": "failed", "datasets": ["com.jpmc.ct.lri.cfg-contractual_cash_flow_results_v1"]},
                {"order": 4, "status": "not_started", "datasets": ["com.jpmc.ct.lri.sls-sls_aws_details_extended_v1"]},
                {"order": 5, "status": "not_started", "datasets": ["com.jpmc.ct.lri.intercompany-intercompany_results"]}
            ],
            "failures": [
                {
                    "dataset_id": "com.jpmc.ct.lri.cfg-contractual_cash_flow_results_v1",
                    "dag_run_id": "FGW_contractual_cash_flow_results_v1_V2_2026-02-21_EMEA_DERIV_CFG_1771403209811",
                    "status": "FAILED",
                    "slice": "EMEA_DERIV_CFG",
                    "created_date": "2026-02-21T05:20:00Z",
                    "updated_date": "2026-02-21T06:45:00Z",
                    "duration_minutes": 85
                }
            ]
        },
        "tool_calls": [
            {"tool": "resolve_batch", "input": {"batch_name": "derivatives"}, "duration_ms": 12},
            {"tool": "get_batch_status", "input": {"dataset_ids": ["..."], "business_date": "2026-02-21", "processing_type": "PRELIM"}, "duration_ms": 340},
            {"tool": "get_batch_progress", "input": {"essential_def": "...", "business_date": "2026-02-21"}, "duration_ms": 280}
        ],
        "suggested_queries": [
            "Show me the failed tasks for the CFG dataset",
            "Has this slice failed before this week?",
            "What about FINAL processing?"
        ]
    }
}
```

**Notes:**
- `structured_data` is optional — only present for status/RCA queries, not general conversation
- `structured_data.type` can be: `batch_status`, `task_details`, `rca_analysis`, `historical_comparison`, `text_only`
- `tool_calls` shows what tools the agent invoked (for UI transparency)
- `suggested_queries` are contextual follow-ups the frontend renders as clickable chips
- If agent encounters an error: `{"thread_id": "...", "response": {"text": "I couldn't query the database: connection timeout...", "error": true}}`

## POST /api/chat/stream (SSE)

Server-Sent Events endpoint for streaming agent responses as they happen.

**Request:** Same JSON body as POST /api/chat, sent as POST JSON body.

**SSE Event Stream:**
```
data: {"type": "node_start", "node": "intent_classifier"}

data: {"type": "node_end", "node": "intent_classifier", "result": {"intent": "status_check"}}

data: {"type": "node_start", "node": "batch_resolver"}

data: {"type": "node_end", "node": "batch_resolver", "result": {"batch": "TB-Derivatives", "dataset_count": 6}}

data: {"type": "node_start", "node": "data_fetcher"}

data: {"type": "tool_call", "tool": "get_batch_status", "status": "executing"}

data: {"type": "tool_result", "tool": "get_batch_status", "row_count": 42}

data: {"type": "node_end", "node": "data_fetcher"}

data: {"type": "node_start", "node": "analyzer"}

data: {"type": "node_end", "node": "analyzer"}

data: {"type": "response", "data": { ... same as POST /api/chat response.response ... }}

data: [DONE]
```

Frontend uses these events to show real-time progress: "Resolving batch... Found 6 datasets... Querying status... Analyzing..."

## GET /api/essentials

Returns current status of ALL monitored essentials. Used by the dashboard table.

**Query Parameters:**
- `business_date` (optional): Default today. Format: YYYY-MM-DD
- `processing_type` (optional): "PRELIM", "FINAL", or omit for both

**Response:**
```json
{
    "business_date": "2026-02-21",
    "timestamp": "2026-02-21T14:30:00Z",
    "summary": {
        "total": 12,
        "completed": 7,
        "running": 3,
        "failed": 1,
        "not_started": 1
    },
    "essentials": [
        {
            "essential_name": "TB-Derivatives",
            "display_name": "Derivatives",
            "status": "PARTIAL_FAILURE",
            "prelim": {
                "status": "PARTIAL_FAILURE",
                "total_datasets": 6,
                "success": 4,
                "failed": 1,
                "running": 1,
                "not_started": 0,
                "progress": "4/6",
                "started_at": "2026-02-21T05:15:00Z",
                "last_updated": "2026-02-21T14:22:00Z",
                "eta": null
            },
            "final": {
                "status": "NOT_STARTED",
                "total_datasets": 6,
                "success": 0,
                "failed": 0,
                "running": 0,
                "not_started": 6,
                "progress": "0/6",
                "started_at": null,
                "last_updated": null,
                "eta": null
            },
            "datasets": [
                {
                    "dataset_id": "com.jpmc.ct.lri.derivatives-slsline_calculator_e15",
                    "sequence_order": 0,
                    "prelim_status": "SUCCESS",
                    "final_status": "NOT_STARTED",
                    "slice_count": 10,
                    "slices_success": 10,
                    "slices_failed": 0,
                    "latest_dag_run_id": "FGW_slsline_calculator_e15_V2_2026-02-21_DERIV-NA-SLICE-1_...",
                    "duration_minutes": 185,
                    "created_date": "2026-02-21T05:15:00Z",
                    "updated_date": "2026-02-21T08:20:00Z"
                }
            ]
        }
    ]
}
```

**Essential-level `status` values:**
- `SUCCESS` — all datasets completed successfully
- `PARTIAL_FAILURE` — at least one dataset failed, others may be running/success
- `FAILED` — critical failure (all or most datasets failed)
- `RUNNING` — at least one dataset still running, none failed
- `NOT_STARTED` — no runs found for this business_date+processing_type
- `WAITING` — predecessor sequence steps not yet complete

## GET /api/status/{essential_name}

Direct status for a single essential (bypasses agent). Used for quick polling.

**Path Parameter:** `essential_name` — common name (e.g., "derivatives", "6G", "SNU")

**Query Parameters:** Same as GET /api/essentials

**Response:** Single essential object from the `essentials` array above.

## GET /api/health

Health check endpoint.

**Response:**
```json
{
    "status": "ok",
    "checks": {
        "fgw_database": "connected",
        "airflow_database": "connected",
        "lenz_api": "reachable",
        "azure_openai": "configured"
    },
    "timestamp": "2026-02-21T14:30:00Z"
}
```

If any check fails:
```json
{
    "status": "degraded",
    "checks": {
        "fgw_database": "connected",
        "airflow_database": "timeout",
        "lenz_api": "reachable",
        "azure_openai": "configured"
    },
    "errors": ["airflow_database: Connection timed out after 5s"],
    "timestamp": "2026-02-21T14:30:00Z"
}
```

## GET /api/lenz/refresh

Force-refresh Lenz API cache for all essentials. Used after batch definitions change.

**Response:**
```json
{
    "refreshed": ["TB-Derivatives", "TB-Securities", "SNU", "SNU-Strategic", ...],
    "failed": [],
    "timestamp": "2026-02-21T14:30:00Z"
}
```
