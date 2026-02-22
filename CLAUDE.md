# SENTRY - SRE Intelligent Batch Monitoring Platform

## Project Overview
SENTRY is an LLM-powered agentic platform for SRE teams at JPMorgan Chase. It monitors batch processing workflows (called "Essentials" or "Asset Classes"), provides status reporting, root cause analysis, runtime prediction, and interactive conversation about system state. Built on LangGraph + LangChain with Azure OpenAI (GPT-4o).

## Tech Stack
- **Backend**: Python 3.11+, FastAPI for API layer
- **Agent Framework**: LangGraph (stateful multi-step orchestration), LangChain (SQL toolkit, tools)
- **LLM**: Azure OpenAI GPT-4o via hybrid auth — SPN certificate Bearer token + API key (see @docs/connectivity.md)
- **Databases**: MySQL (RDS Aurora) — two databases: `FINEGRAINED_WORKFLOW` and `airflow`
- **External APIs**: Lenz API for batch definitions
- **UI**: React + TypeScript, following LRI-Labs design system (see @docs/ui-design.md)
- **Memory**: LangGraph MemorySaver (in-memory session checkpointing for Phase 1). Redis planned for Phase 2+ when multi-user/multi-process needed.

## Project Structure
```
sentry/
├── CLAUDE.md                    # This file
├── docs/                        # Detailed architecture docs (@-reference these)
│   ├── architecture.md          # Full system architecture and LangGraph design
│   ├── data-model.md            # Database schemas, table relationships, domain mappings
│   ├── lenz-integration.md      # Lenz API integration details
│   ├── query-tier-system.md     # Tier 1/2/3 query architecture
│   ├── ui-design.md             # UI design system and component specs
│   ├── ui-reference.html        # Working HTML mockup — THE visual reference
│   ├── connectivity.md          # RDS, Azure OpenAI, AWS connection details
│   ├── api-contracts.md         # API endpoint request/response JSON shapes
│   └── implementation-plan.md   # Phased implementation with checkboxes
├── backend/
│   ├── agent/                   # LangGraph agent definition
│   │   ├── graph.py             # Main LangGraph state machine
│   │   ├── nodes/               # Agent nodes (intent_classifier, batch_resolver, etc.)
│   │   ├── tools/               # Agent tools (batch_query, task_query, etc.)
│   │   └── state.py             # Agent state definition
│   ├── services/
│   │   ├── lenz_service.py      # Lenz API client with caching
│   │   ├── db_service.py        # Database connection pool (SQLAlchemy)
│   │   └── azure_openai.py      # LLM client
│   ├── config/
│   │   ├── essentials_map.py    # Batch name → Lenz essential name mapping
│   │   ├── domain_rules.py      # TRIGGER_TYPE mappings, DAG_RUN_ID format, etc.
│   │   └── sql_examples.json    # Few-shot SQL examples for Tier 2
│   ├── api/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── routes/              # API routes (chat, status, metrics)
│   │   └── streaming.py         # SSE (Server-Sent Events) for streaming agent responses
│   └── models/                  # Pydantic data models
├── frontend/
│   ├── src/
│   │   ├── components/          # React components
│   │   ├── pages/               # Dashboard, BatchExplorer, RCA, etc.
│   │   ├── hooks/               # Custom hooks (useChat, useBatchStatus, etc.)
│   │   └── styles/              # CSS following LRI-Labs design tokens
│   └── package.json
├── tests/
└── requirements.txt
```

## Critical Domain Rules — NEVER VIOLATE THESE
1. **Batch → Dataset mapping**: A batch (Essential) is an ARBITRARY grouping of datasets. Dataset IDs do NOT follow naming patterns. ALWAYS resolve batch→datasets via Lenz API. NEVER use `output_dataset_id LIKE '%batch_name%'`.
2. **TRIGGER_TYPE mapping**: `ProcessTrigger` = PRELIM, `RerunTrigger` = FINAL, `ManualTrigger` = MANUAL. This is absolute.
3. **DAG_RUN_ID format**: `FGW_{dag_id}_{business_date}_{SLICE_NAME}_{unique_integer}`. Parse slices from this structure.
4. **Cross-DB join**: `FINEGRAINED_WORKFLOW.WORKFLOW_RUN_INSTANCE.DAG_RUN_ID` = `airflow.task_instance.run_id`
5. **Latest run logic**: For any dataset+business_date combo, there can be multiple runs. Use `ROW_NUMBER() OVER(PARTITION BY OUTPUT_DATASET_ID, TRIGGER_TYPE ORDER BY CREATED_DATE DESC) = 1` for latest. For slice-specific filtering, use `dag_run_id LIKE '%{slice_name}%'` with known slices from Lenz API — NEVER parse slices from DAG_RUN_ID with substring operations.
6. **Business date filter**: EVERY query to WORKFLOW_RUN_INSTANCE MUST filter on `business_date`. No full table scans.

## Essential Name Mapping (EXACT — do not assume others)
```python
ESSENTIAL_MAP = {
    "6G": "6G-FR2052a-E2E",
    "FR2052A": "6G-FR2052a-E2E",
    "PBSYNTHETICS": "PBSynthetics",
    "SNU": "SNU",
    "SNU STRATEGIC": "SNU-Strategic",
    "SNU REG STRATEGIC": "SNU-REG-STRATEGIC",
    "COLLATERAL": "TB-Collateral",
    "DERIVATIVES": "TB-Derivatives",
    "DERIV": "TB-Derivatives",
    "SECURITIES": "TB-Securities",
    "SECFIN": "TB-SecFIn",
    "CFG": "TB-CFG",
    "SMAA": "TB-SMAA",
    "UPC": "UPC",
}
```

## Commands
- `cd backend && uvicorn api.main:app --reload --port 8000`: Start backend API server
- `cd frontend && npm run dev`: Start frontend dev server (separate terminal)
- `cd backend && python -m pytest tests/`: Run backend tests
- `cd frontend && npm run build`: Build frontend for production

## Code Style
- Python: Black formatter, 100 char line limit, type hints on all functions
- Use `async/await` for all I/O operations (DB, API calls, LLM)
- React: Functional components with TypeScript, CSS modules
- All SQL queries must be parameterized — NEVER use f-strings for SQL
- Every LangGraph tool must have explicit error handling and timeout

## Important Gotchas
- **create_llm() must be called per graph invocation** — do NOT store the LLM as a global singleton. The Bearer token expires. Call `create_llm()` from `azure_openai.py` before each `graph.invoke()`. The CertificateCredential itself is cached internally, so this is cheap.
- **RDS_PASSWORD is an IAM token, not a static password.** It lasts 6+ hours. Must be single-quoted in `.env`. `URL.create()` handles encoding. `pool_recycle=18000` and `pool_pre_ping=True` are mandatory. See @docs/connectivity.md.
- The Lenz API response nests under `"GLOBAL" → {essential_name} → "schemaJson" → "datasets"`
- Some datasets have `sliceGroups` with named groups (e.g., "DERIV": [...]), others have flat `"slices": [...]`
- WORKFLOW_RUN_INSTANCE has no explicit `start_time`/`end_time` — derive from CREATED_DATE and UPDATED_DATE
- The airflow database `task_instance` table uses `run_id` (not `dag_run_id`) as the column name
- Read @docs/data-model.md for full schema details before writing ANY database queries
