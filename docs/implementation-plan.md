# SENTRY Implementation Plan

## Phase 1: Core Status Reporting + Basic RCA (Weeks 1-6)

### 1.1 Project Setup
- [x] Initialize Python project with pyproject.toml (Python 3.11+)
- [x] Set up FastAPI backend skeleton with `uvicorn` entry point
- [x] Create requirements.txt with all dependencies (fastapi, uvicorn[standard], sse-starlette, langgraph, langchain, langchain-openai, langchain-community, sqlalchemy, pymysql, pydantic, python-dotenv, httpx, httpx-ntlm, requests, requests-ntlm, cryptography, sqlparse, azure-identity, jinja2)
- [x] Create .env.example with all required variables
- [x] Set up frontend directory: frontend/templates/ (Jinja2) + frontend/static/ (CSS, JS) — served by FastAPI, no build step
- [x] Configure SQLAlchemy connection pools for both databases (FINEGRAINED_WORKFLOW, airflow)
- [x] Verify RDS connectivity with test queries
- [x] Configure Azure OpenAI client with hybrid auth (follow EXACT pattern from @docs/connectivity.md — SPN cert Bearer token + API key via default_headers)
- [ ] Set up LangSmith/LangFuse for agent tracing

### 1.2 Lenz Service
- [x] Implement LenzService class with caching (@docs/lenz-integration.md)
- [x] Implement ESSENTIAL_MAP name resolution with fuzzy matching
- [x] Implement Lenz API response parser (handle all 3 sliceGroups formats)
- [x] Implement EssentialDef and DatasetDef Pydantic models
- [x] Implement cache with TTL (default 300s)
- [x] Pre-fetch all essentials on startup
- [x] Add /api/lenz/refresh endpoint for manual cache invalidation
- [x] Write tests: name resolution, response parsing, cache behavior

### 1.3 Tier 1 Tools (Parameterized Queries)
- [x] Implement get_batch_status tool
- [x] Implement get_task_details tool
- [x] Implement get_slice_status tool
- [x] Implement get_batch_progress tool (sequence-aware)
- [x] Add query timeout (10s) and LIMIT (500) enforcement
- [x] Add comprehensive error handling (connection failures, empty results, timeouts)
- [x] Write tests with sample data from @docs/data-model.md

### 1.4 LangGraph Agent
- [x] Define SentryState TypedDict
- [x] Implement intent_classifier node
- [x] Implement batch_resolver node (calls LenzService)
- [x] Implement data_fetcher node (calls Tier 1 tools)
- [x] Implement analyzer node (sequence-aware status aggregation)
- [x] Implement response_synthesizer node
- [x] Define conditional edges (see @docs/architecture.md for routing)
- [x] Set up LangGraph MemorySaver (in-memory checkpointing) for session state
- [x] Implement conversation context management (remembers batch + date across turns via thread_id)
- [ ] Write integration tests: full agent flow for status query

### 1.5 Backend API
- [x] FastAPI app with Jinja2 template engine and static file mounting
- [x] GET / route serving dashboard.html template
- [x] Implement all endpoints per @docs/api-contracts.md:
- [x] POST /api/chat — main chat endpoint (accepts message, returns agent response with structured_data, tool_calls, suggested_queries)
- [x] POST /api/chat/stream — SSE streaming responses with node-level progress events
- [x] GET /api/status/{essential_name} — direct status endpoint (bypasses agent)
- [x] GET /api/essentials — list all essentials with current status, dataset-level detail
- [x] GET /api/health — health check (DB connectivity, Lenz reachability, Azure OpenAI config)
- [x] GET /api/lenz/refresh — force-refresh Lenz cache

### 1.6 Frontend — Dashboard (Vanilla HTML/CSS/JS + Jinja2)
- [x] Create frontend/templates/ and frontend/static/ directory structure
- [x] base.html: Jinja2 base template with head, Google Fonts, CSS/JS includes, layout shell
- [x] sentry.css: Single stylesheet with ALL LRI-Labs design tokens from @docs/ui-design.md
- [x] partials/header.html: Header bar (brand, nav tabs, env badge, connection dot, icons)
- [x] partials/summary_cards.html: 5 summary stat cards with IDs for JS updates
- [x] partials/essentials_table.html: Data table with expandable rows, populated by JS
- [x] dashboard.js: Fetch /api/essentials, render table rows, expand/collapse, toggles, refresh
- [x] utils.js: Shared helpers (formatDate, generateUUID, formatDuration, DOM helpers)
- [x] Status badges, Prelim/Final dots, progress bars — all in sentry.css
- [x] Date picker and PRELIM/FINAL/ALL toggle wired to re-fetch API
- [x] Auto-refresh via setInterval (60s default)
- [x] **IMPORTANT**: Match @docs/ui-reference.html PIXEL-PERFECTLY

### 1.7 Frontend — Chat Panel (Vanilla JS + EventSource SSE)
- [x] partials/chat_panel.html: Chat panel structure (header, context bar, messages, input)
- [x] chat.js: Full chat logic — message rendering, send flow, tool call cards, data cards
- [x] SSE streaming via fetch() ReadableStream for POST-based /api/chat/stream
- [x] Thinking indicator with animated dots and dynamic status text
- [x] Suggested query chips (clickable, pre-fill and send)
- [x] Tool call display cards (collapsible, monospace)
- [x] Inline data cards with severity left-border (red/orange/blue)
- [x] Thread ID management (UUID per conversation, new chat button resets)
- [x] Context bar synced with dashboard date picker and processing type toggle
- [x] "Ask SENTRY AI" button in expanded rows → pre-fills and sends chat query

## Phase 2: Tier 2 SQL Analyst (Weeks 7-10)

### 2.1 Tier 2 Constrained SQL
- [ ] Implement ConstrainedSQLExecutor with all guardrails
- [ ] Auto-discover schema via LangChain SQLDatabase at startup
- [x] Build domain_rules.py with static rules (TRIGGER_TYPE, DAG_RUN_ID format, etc.)
- [ ] Create sql_examples.json with 15-20 curated question→SQL pairs
- [ ] Set up InMemoryVectorStore for few-shot retrieval
- [ ] Implement sql_analyst LangGraph node
- [ ] Add Tier 2 routing in intent_classifier (detect novel analytical questions)
- [ ] SQL validation: AST parsing, table whitelist, LIMIT injection
- [ ] Logging: every Tier 2 query logged with input, generated SQL, results

### 2.2 Fast-Path Cache (Optional)
- [ ] Set up Redis locally
- [ ] Redis-backed status cache for all essentials
- [ ] Background refresh every 60 seconds
- [ ] GET /api/status endpoint serves from cache (sub-100ms response)
- [ ] Agent uses cache for simple status queries, DB for drill-downs
- [ ] Optionally upgrade LangGraph checkpointer from MemorySaver to RedisSaver

## Phase 3: Runtime Prediction (Weeks 11-16)

### 3.1 Historical Data Pipeline
- [ ] Build data collection: store runtime per dataset/slice for each business_date
- [ ] Historical query: pull last 30+ business_dates of runtime data
- [ ] Compute statistics: P50, P90, P95 runtime per dataset/slice
- [ ] Store in analytics tables (storage backend TBD — SQLite, dedicated RDS schema, or PostgreSQL)

### 3.2 Prediction Model
- [ ] Percentile-based ETA ("this DAG is at P75 runtime, expect completion in ~30min")
- [ ] Detect outliers ("this DAG is running 2x longer than P90")
- [ ] Feed predictions to response_synthesizer for ETA responses
- [ ] Display predicted vs actual in UI

## Phase 4: AWS Diagnostics (Weeks 17-20)

**Prerequisites — must be provided before starting this phase:**
- RDS instance identifier (for CloudWatch RDS metrics)
- SQS queue name(s) to monitor
- AWS IAM credentials with CloudWatch read access
- Confirmation of which metrics are relevant for RCA

### 4.1 AWS Metrics Integration
- [ ] Implement CloudWatch client (boto3)
- [ ] Implement get_cloudwatch_metrics tool for RDS (ReadLatency, WriteLatency, CPUUtilization, FreeableMemory, DatabaseConnections)
- [ ] Implement get_cloudwatch_metrics tool for SQS (ApproximateAgeOfOldestMessage, ApproximateNumberOfMessagesVisible, NumberOfMessagesInFlight)
- [ ] Time window derivation from DAG CREATED_DATE/UPDATED_DATE
- [ ] Anomaly detection: compare metric values against rolling baseline
- [ ] Add aws_diagnostics node to LangGraph
- [ ] Add aws_diagnostics intent to intent_classifier
- [ ] Route: failures in analyzer → aws_diagnostics → response_synthesizer
- [ ] Report CORRELATION not causation in responses

## Phase 5: Production Readiness (Weeks 21+)

- [ ] Proactive monitoring: background service polling batch progress
- [ ] Alerting: Slack webhook integration for failures and SLA breaches
- [ ] RBAC: LDAP/AD group-based access control per essential
- [ ] Audit log: persist all agent traces, queries, and responses
- [ ] EKS deployment: Helm charts, ConfigMaps for env vars
- [ ] Load testing: verify agent latency under concurrent users
- [ ] Runbook: operational documentation for SENTRY itself
