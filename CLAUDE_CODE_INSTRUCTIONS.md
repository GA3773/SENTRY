# SENTRY — Claude Code Development Guide

## Pre-Requisites

Before starting, ensure you have installed:
- Python 3.11+
- Node.js 18+
- Git
- Claude Code (`npm install -g @anthropic-ai/claude-code`)

Have these credentials ready (DO NOT paste them into Claude Code chat — only into .env file):
- RDS MySQL: host, port, username, password, PEM file path
- Azure OpenAI: API key, endpoint, deployment name
- AWS: access key ID, secret access key, region
- Network access to lenz-app.prod.aws.jpmchase.net (JPMC VPN)

---

## Initial Setup

```bash
# 1. Unzip and enter project
unzip sentry-project.zip
cd sentry-project

# 2. Initialize git (Claude Code works best inside a git repo)
git init
git add .
git commit -m "Initial SENTRY project scaffold with architecture docs"

# 3. Launch Claude Code
claude
```

Claude Code will auto-read CLAUDE.md on startup. Verify by asking:
```
What essentials does SENTRY monitor? What is the tech stack?
```

---

## Session 1 — Backend Scaffold

**Prompt:**
```
Read @docs/implementation-plan.md section 1.1.

Create the backend project structure under backend/ as defined in CLAUDE.md.
- pyproject.toml with Python 3.11+ and these dependencies: fastapi, uvicorn[standard], sse-starlette, langgraph, langchain, langchain-openai, langchain-community, sqlalchemy, pymysql, pydantic, python-dotenv, httpx, cryptography, sqlparse
- Also create requirements.txt with the same dependencies
- Create the folder structure: agent/ (with nodes/, tools/, graph.py, state.py), services/, config/, api/ (with routes/), models/
- Create .env.example from @docs/connectivity.md
- Create api/main.py with a basic FastAPI app that has:
  - GET /api/health endpoint returning {"status": "ok"}
  - CORS middleware allowing localhost:5173 (Vite default)
- Do NOT set up Docker or Redis. This runs locally via uvicorn.

Check off completed items in @docs/implementation-plan.md.
```

**After session:**
```bash
cd backend
cp .env.example .env
# Edit .env with your actual credentials
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
# Verify: curl http://localhost:8000/api/health
```

```bash
git add . && git commit -m "Session 1: Backend scaffold with FastAPI"
```

---

## Session 2 — Database Connectivity

**Prompt:**
```
Read @docs/connectivity.md and @docs/data-model.md.

Implement backend/services/db_service.py:
- Create SQLAlchemy connection pools for both databases (FINEGRAINED_WORKFLOW and airflow)
- Use the RDS connection pattern from https://raw.githubusercontent.com/GA3773/Comm/refs/heads/main/backend/db.py
- Load credentials from .env using python-dotenv
- SSL connection using the PEM file
- Both connections must be READ-ONLY in practice

Create a test script backend/tests/test_db_connectivity.py that:
- Connects to FINEGRAINED_WORKFLOW and runs: SELECT COUNT(*) FROM WORKFLOW_RUN_INSTANCE WHERE business_date = CURDATE()
- Connects to airflow and runs: SELECT COUNT(*) FROM task_instance LIMIT 1
- Prints results to verify connectivity

Do NOT proceed to anything else. Database connectivity is the first gate.
```

**After session:**
```bash
cd backend && python tests/test_db_connectivity.py
# Must see row counts printed. If this fails, fix before proceeding.
```

```bash
git add . && git commit -m "Session 2: Database connectivity verified"
```

---

## Session 3 — Lenz API Service

**Prompt:**
```
Read @docs/lenz-integration.md thoroughly.

Implement backend/services/lenz_service.py:
- LenzService class with in-memory caching (TTL from .env LENZ_CACHE_TTL, default 300s)
- ESSENTIAL_MAP from CLAUDE.md (the exact mapping — 6G, DERIVATIVES, SNU, etc.)
- Name resolution with case-insensitive fuzzy matching
- Lenz API call to /essentials/def?name={essential_name} using httpx (async). 
  Do NOT use the requests library. See @docs/connectivity.md Lenz section for the exact pattern.
- Response parser that handles ALL THREE sliceGroups formats:
  1. Flat: {"slices": ["PB-GLOBAL-SLICE", ...]}
  2. Named group: {"DERIV": ["AWS_OTC_DERIV_AGG_EMEA", ...]}
  3. Missing: no sliceGroups key at all
- EssentialDef and DatasetDef Pydantic models as shown in the doc
- Methods: get_essential_definition(), get_dataset_ids(), get_datasets_by_sequence(), get_valid_slices()
- resolve_slice_filter() for fuzzy slice matching (user says "EMEA" → finds all EMEA slices)

Implement backend/config/essentials_map.py with the ESSENTIAL_MAP dict.

Create backend/tests/test_lenz_service.py that:
- Fetches TB-Derivatives definition and prints dataset count, all dataset IDs, and sequence order
- Fetches SNU definition and verifies it has 22+ datasets with mixed namespaces (datasets span lri.upc, lri.derivatives, lri.snu, etc.)
- Fetches SNU-Strategic separately and verifies it returns a different set of datasets
- Tests name resolution: "6G" → "6G-FR2052a-E2E", "DERIV" → "TB-Derivatives"
- Tests slice resolution: "EMEA" for intercompany dataset returns EMEA slices

Run the tests and make sure they pass.
```

**After session:**
```bash
cd backend && python tests/test_lenz_service.py
```

```bash
git add . && git commit -m "Session 3: Lenz API service with caching"
```

---

## Session 4 — Tier 1 Query Tools

**Prompt:**
```
Read @docs/query-tier-system.md (Tier 1 section) and @docs/data-model.md.

Implement the Tier 1 parameterized query tools in backend/agent/tools/:

1. backend/agent/tools/batch_tools.py:
   - get_batch_status(dataset_ids, business_date, processing_type, status_filter, limit)
     Queries WORKFLOW_RUN_INSTANCE with IN clause for dataset_ids. Maps processing_type to TRIGGER_TYPE.
   - get_batch_progress(essential_def, business_date, processing_type)
     Sequence-aware progress. Groups results by sequenceOrder from Lenz. Returns per-step status.
   - get_slice_status(dataset_id, business_date, slice_patterns, processing_type)
     Filters by DAG_RUN_ID LIKE patterns for specific slices.
   - get_historical_runs(dataset_id, last_n_business_dates, processing_type)
     For trend analysis across multiple business dates.

2. backend/agent/tools/task_tools.py:
   - get_task_details(dag_run_id, state_filter)
     Queries airflow.task_instance WHERE run_id = dag_run_id.

CRITICAL RULES (from CLAUDE.md — re-read them):
- ALL queries MUST filter on business_date
- ALL queries MUST have LIMIT 500
- ALL queries use parameterized %s placeholders — NEVER f-strings for SQL
- TRIGGER_TYPE mapping: ProcessTrigger=PRELIM, RerunTrigger=FINAL, ManualTrigger=MANUAL
- Each tool must have try/except with timeout handling

Implement backend/config/domain_rules.py with:
- TRIGGER_TYPE_MAP dict
- DAG_RUN_ID format documentation as constants/comments

Create backend/tests/test_tools.py that tests:
- get_batch_status for DERIVATIVES on a recent business date
- get_task_details for a known DAG_RUN_ID from the sample data in data-model.md
- Verify LIMIT is always applied
- Verify TRIGGER_TYPE mapping works correctly
```

**After session:**
```bash
cd backend && python -m pytest tests/test_tools.py -v
```

```bash
git add . && git commit -m "Session 4: Tier 1 parameterized query tools"
```

---

## Session 5 — LangGraph Agent + Azure OpenAI

**Prompt:**
```
Read @docs/architecture.md — focus on Layer 3 (Agent Orchestration).
Read @docs/connectivity.md — Azure OpenAI section.

This session builds the complete LangGraph agent WITH LLM integration end-to-end.

STEP 1: Azure OpenAI client (needed by agent nodes)

Implement backend/services/azure_openai.py:
- Follow the EXACT connection pattern from https://raw.githubusercontent.com/GA3773/COST_AGENT_AWS/refs/heads/main/services/azure_openai.py
- Create AzureChatOpenAI instance using langchain_openai
- Load credentials from .env
- temperature=0 for deterministic responses
- timeout=30
- Export a get_llm() function that returns the configured instance

STEP 2: Agent state and nodes

1. backend/agent/state.py:
   - SentryState TypedDict as defined in architecture.md

2. backend/agent/nodes/:
   - intent_classifier.py: Uses the LLM to classify user intent into: status_check, rca_drilldown, task_detail, general_query, out_of_scope
     NOTE: "prediction" intent exists in the architecture but is NOT implemented until Phase 3.
     For now, if the classifier detects a prediction question, route it to response_synthesizer
     with a message like "Runtime prediction is coming in a future release."
   - batch_resolver.py: Extracts batch name from message, calls LenzService, populates state with batch_definition and dataset_ids
   - data_fetcher.py: Calls appropriate Tier 1 tools based on intent and resolved batch
   - analyzer.py: Groups results by sequence order, identifies failures/completions, computes progress ("step 3 of 6"), flags anomalies
   - response_synthesizer.py: Uses the LLM to generate natural language summaries from structured data, includes suggested follow-up queries

3. backend/agent/graph.py:
   - Build the LangGraph StateGraph with all nodes
   - Conditional edges as defined in architecture.md:
     - status_check → batch_resolver → data_fetcher → analyzer → response_synthesizer
     - rca_drilldown → batch_resolver → data_fetcher → analyzer → response_synthesizer
     - task_detail → data_fetcher → response_synthesizer
     - general_query → batch_resolver → response_synthesizer (Tier 2 comes later)
     - out_of_scope → response_synthesizer
   - If analyzer finds failures during status_check, route to response_synthesizer with RCA context
   - Compile with MemorySaver checkpointing:
     from langgraph.checkpoint.memory import MemorySaver
     checkpointer = MemorySaver()
     graph = workflow.compile(checkpointer=checkpointer)

STEP 3: Wire into FastAPI (follow @docs/api-contracts.md for exact request/response shapes):
   - POST /api/chat in api/main.py
     Accepts: {"message": str, "thread_id": str, "business_date": optional, "processing_type": optional}
     Returns: {"thread_id": str, "response": {"text": str, "structured_data": optional, "tool_calls": list, "suggested_queries": list}}
   - GET /api/chat/stream as SSE endpoint for streaming node updates (use sse-starlette)
   - GET /api/health returning connectivity checks for both DBs, Lenz, and Azure OpenAI

Test by starting uvicorn and sending:
  curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message": "How is derivatives doing today?", "thread_id": "test-1"}'

Then test conversation continuity:
  curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message": "What about the EMEA slices?", "thread_id": "test-1"}'

The second call should remember the context (DERIVATIVES, today's date) from the first.

Then test a different essential:
  curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message": "What is the status of SNU today?", "thread_id": "test-2"}'

Should return a natural language response about SNU batch status with dataset-level details.
```

**After session:**
```bash
cd backend && uvicorn api.main:app --reload --port 8000
# Test with the curl commands above
```

```bash
git add . && git commit -m "Session 5: LangGraph agent with Azure OpenAI, end-to-end working"
```

---

## Session 6 — Frontend Dashboard

**Prompt:**
```
Read @docs/ui-design.md for ALL design tokens and component specs.
Open @docs/ui-reference.html in a browser — THIS is the exact UI to replicate.

Set up the frontend:
- cd frontend && npm create vite@latest . -- --template react-ts
- Install dependencies: npm install
- Clean out default Vite boilerplate

Build the dashboard matching ui-reference.html PIXEL-PERFECTLY:

1. Design tokens as CSS variables (EXACT hex values from ui-design.md)
2. Import Google Fonts: Source Sans 3 (300-700) and JetBrains Mono (400,500)
3. Header component: dark bg #1a2e3b, "SENTRY" brand, nav tabs with teal underlines, PROD badge, connection dot
4. Summary cards row: 5 cards (Total, Completed, Running, Failed, Not Started)
5. Essentials data table:
   - Columns: Essential, Status, Prelim/Final, Progress, Datasets, Started, Last Updated, ETA
   - Expandable rows with chevron arrow
   - Expanded view: dataset table with sequence badges, slice counts, quick action buttons
   - Status badges with colored dots (SUCCESS=teal, FAILED=red, RUNNING=blue animated, etc.)
   - Prelim/Final indicator dots
   - Progress bars with fraction text
6. Page controls: PRELIM/FINAL/ALL toggle, date picker, refresh button
7. All data is mock/static for now — we will connect to API in the next session.
   IMPORTANT: Structure mock data to match @docs/api-contracts.md GET /api/essentials response shape
   exactly. This ensures seamless API integration in the next session.

The frontend runs on Vite dev server (port 5173) — NOT served by the backend.
Configure Vite to proxy /api requests to http://localhost:8000.

CRITICAL: Do not use any component library (no MUI, no Ant Design, no Chakra). 
This is custom CSS matching the LRI-Labs design system. Use CSS modules or a single 
global stylesheet with the design tokens from ui-design.md.
```

**After session:**
```bash
cd frontend && npm run dev
# Open http://localhost:5173 — compare side-by-side with docs/ui-reference.html
```

```bash
git add . && git commit -m "Session 6: Dashboard UI matching LRI-Labs design system"
```

---

## Session 7 — Chat Panel + API Integration

**Prompt:**
```
Read @docs/ui-design.md — Chat Panel section.
Read @docs/api-contracts.md — POST /api/chat response shape and GET /api/chat/stream SSE events.
Reference @docs/ui-reference.html for the exact chat panel design.

Build the SENTRY AI chat panel on the right side of the dashboard:

1. Split-panel layout: dashboard (flex:1) left, chat panel (420px) right
2. Chat header: "SENTRY AI" with connection status dot, new chat / history / expand buttons
3. Context bar: shows active date and environment as teal tags
4. Message area:
   - Assistant messages: left-aligned, #f4f6f8 bubble
   - User messages: right-aligned, #1a2e3b bubble
   - Tool call display cards: bordered, monospace, collapsible (show which tools the agent called)
   - Inline data cards: white bg with severity left-border (red=high, orange=medium)
   - Suggested query chips: teal pills, clickable (pre-fills input)
5. Thinking indicator: three animated dots
6. Input area: textarea with send button, keyboard hint line
7. Connect to backend using EventSource (SSE) on GET /api/chat/stream for real-time
   node progress ("Resolving batch... Querying status... Analyzing...").
   Fall back to POST /api/chat for non-streaming responses.
8. Use thread_id (generate UUID per conversation) for session continuity
9. "Ask SENTRY AI" button in expanded table rows should open chat with pre-filled context

Also connect the dashboard table to GET /api/essentials backend endpoint:
- Read @docs/api-contracts.md for the exact response shape
- Create GET /api/essentials in the backend that:
  - Fetches all essentials from Lenz
  - Queries WORKFLOW_RUN_INSTANCE for today's status for each
  - Returns structured data matching the contract in api-contracts.md
- Create GET /api/status/{essential_name} for single-essential quick polling
- Replace mock data in the dashboard with live API data

Both backend (port 8000) and frontend (port 5173) should be running.
```

**After session:**
```bash
# Terminal 1
cd backend && uvicorn api.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev

# Open http://localhost:5173 — full working dashboard with live data and chat
```

```bash
git add . && git commit -m "Session 7: Chat panel, API integration, live dashboard data"
```

---

## Session 8 — Tier 2 SQL Analyst

**Prompt:**
```
Read @docs/query-tier-system.md — Tier 2 section completely.

Implement Tier 2 constrained LLM SQL:

1. backend/agent/tools/sql_analyst_tool.py:
   - ConstrainedSQLExecutor class with ALL guardrails:
     - ALLOWED_TABLES whitelist
     - FORBIDDEN_KEYWORDS check
     - SQL AST validation via sqlparse (already in requirements)
     - LIMIT injection if missing (max 500)
     - 10 second query timeout
     - Read-only connection

2. backend/config/sql_examples.json:
   - 15-20 curated question→SQL pairs covering these patterns:
     a. Single-batch status with TRIGGER_TYPE filter
     b. Duration calculation (TIMESTAMPDIFF)
     c. Multi-dataset aggregation with IN clause
     d. Slice-level filtering via DAG_RUN_ID
     e. Cross-database query using run_id join
     f. Historical lookback across business_dates
     g. Failure analysis with GROUP BY
     h. Task-level drill-down

3. Schema auto-discovery at startup using langchain_community.utilities.SQLDatabase:
   - Connect to both databases
   - Get table info with 3 sample rows
   - Store as schema context string

4. backend/agent/nodes/sql_analyst.py:
   - Assembles 3-layer prompt: auto-discovered schema + static domain rules + 3 most similar examples
   - CRITICAL: batch→dataset resolution via Lenz BEFORE SQL generation
   - Injects resolved dataset IDs as FACT into prompt
   - Generates SQL → validates → executes → returns results

5. Update LangGraph graph:
   - intent_classifier routes general_query → batch_resolver → sql_analyst → response_synthesizer
   - Log every Tier 2 query (input question, generated SQL, results)

Test with analytical queries that Tier 1 cannot handle:
- "Which batch took longest to complete PRELIM yesterday?"
- "Has DERIV-NA-SLICE-2 failed in the last 10 business dates?"
- "Average runtime per slice for EMEA vs APAC this week"
```

**After session:**
```bash
git add . && git commit -m "Session 8: Tier 2 constrained SQL analyst with guardrails"
```

---

## Running SENTRY

After all sessions are complete:

```bash
# Terminal 1 — Backend
cd sentry-project/backend
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend
cd sentry-project/frontend
npm run dev
```

Open http://localhost:5173 in your browser.

---

## Troubleshooting Tips for Claude Code Sessions

**If Claude Code seems to have forgotten project context:**
```
Re-read CLAUDE.md and confirm the critical domain rules — especially 
the batch→dataset mapping rule and TRIGGER_TYPE mapping.
```

**If Claude Code writes SQL with LIKE for batch filtering:**
```
STOP. Read CLAUDE.md critical rule #1. Batches are arbitrary groupings. 
NEVER use LIKE for batch filtering. Always resolve via Lenz API and use 
IN clause with exact dataset IDs.
```

**If a session gets long and responses degrade:**
```bash
# Commit what you have, then start fresh
git add . && git commit -m "WIP: description"
/clear
# Re-orient in the new session:
Check @docs/implementation-plan.md for progress. Continue with next unchecked items.
```

**If you need to reference a specific doc mid-session:**
```
Read @docs/data-model.md before writing this query — check the column semantics table.
```

**Use `ultrathink` for complex architectural decisions:**
```
ultrathink — Read @docs/architecture.md and implement the LangGraph conditional 
routing logic. Multiple nodes need to chain correctly.
```
