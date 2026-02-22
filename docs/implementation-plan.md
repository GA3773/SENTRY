# SENTRY Implementation Plan

## Phase 1: Core Status Reporting + Basic RCA (Weeks 1-6)

### 1.1 Project Setup
- [x] Initialize Python project with pyproject.toml (Python 3.11+)
- [x] Set up FastAPI backend skeleton with `uvicorn` entry point
- [x] Create requirements.txt with all dependencies (fastapi, uvicorn[standard], sse-starlette, langgraph, langchain, langchain-openai, langchain-community, sqlalchemy, pymysql, pydantic, python-dotenv, httpx, cryptography, sqlparse)
- [x] Create .env.example with all required variables
- [ ] Set up React + TypeScript frontend with Vite (runs separately via `npm run dev`)
- [x] Configure SQLAlchemy connection pools for both databases (FINEGRAINED_WORKFLOW, airflow)
- [x] Verify RDS connectivity with test queries
- [ ] Configure Azure OpenAI client (follow pattern from @docs/connectivity.md)
- [ ] Set up LangSmith/LangFuse for agent tracing

### 1.2 Lenz Service
- [ ] Implement LenzService class with caching (@docs/lenz-integration.md)
- [ ] Implement ESSENTIAL_MAP name resolution with fuzzy matching
- [ ] Implement Lenz API response parser (handle all 3 sliceGroups formats)
- [ ] Implement EssentialDef and DatasetDef Pydantic models
- [ ] Implement cache with TTL (default 300s)
- [ ] Pre-fetch all essentials on startup
- [ ] Add /api/lenz/refresh endpoint for manual cache invalidation
- [ ] Write tests: name resolution, response parsing, cache behavior

### 1.3 Tier 1 Tools (Parameterized Queries)
- [ ] Implement get_batch_status tool
- [ ] Implement get_task_details tool
- [ ] Implement get_slice_status tool
- [ ] Implement get_batch_progress tool (sequence-aware)
- [ ] Add query timeout (10s) and LIMIT (500) enforcement
- [ ] Add comprehensive error handling (connection failures, empty results, timeouts)
- [ ] Write tests with sample data from @docs/data-model.md

### 1.4 LangGraph Agent
- [ ] Define SentryState TypedDict
- [ ] Implement intent_classifier node
- [ ] Implement batch_resolver node (calls LenzService)
- [ ] Implement data_fetcher node (calls Tier 1 tools)
- [ ] Implement analyzer node (sequence-aware status aggregation)
- [ ] Implement response_synthesizer node
- [ ] Define conditional edges (see @docs/architecture.md for routing)
- [ ] Set up LangGraph MemorySaver (in-memory checkpointing) for session state
- [ ] Implement conversation context management (remembers batch + date across turns via thread_id)
- [ ] Write integration tests: full agent flow for status query

### 1.5 Backend API
- [ ] FastAPI app with CORS configuration
- [ ] Implement all endpoints per @docs/api-contracts.md:
- [ ] POST /api/chat — main chat endpoint (accepts message, returns agent response with structured_data, tool_calls, suggested_queries)
- [ ] GET /api/chat/stream — SSE streaming responses with node-level progress events
- [ ] GET /api/status/{essential_name} — direct status endpoint (bypasses agent)
- [ ] GET /api/essentials — list all essentials with current status, dataset-level detail
- [ ] GET /api/health — health check (DB connectivity, Lenz reachability, Azure OpenAI config)
- [ ] GET /api/lenz/refresh — force-refresh Lenz cache

### 1.6 Frontend — Dashboard
- [ ] React + TypeScript project setup (Vite)
- [ ] Implement LRI-Labs design system tokens as CSS variables (EXACT values from @docs/ui-design.md)
- [ ] Import Source Sans 3 and JetBrains Mono fonts
- [ ] Header component (brand, nav, env badge, icons)
- [ ] Summary cards row (total, completed, running, failed, not started)
- [ ] Essentials data table with expandable rows
- [ ] Expanded row: dataset table with sequence badges, slice counts
- [ ] Status badges component (SUCCESS, FAILED, RUNNING, etc.)
- [ ] Prelim/Final indicator dots
- [ ] Progress bar component
- [ ] Date picker and processing type toggle (PRELIM/FINAL/ALL)
- [ ] Auto-refresh mechanism (configurable interval)
- [ ] **IMPORTANT**: Match @docs/ui-reference.html PIXEL-PERFECTLY

### 1.7 Frontend — Chat Panel
- [ ] Split-panel layout (dashboard left, chat right)
- [ ] Chat header with connection status
- [ ] Context bar with active filters (date, env)
- [ ] Message bubbles (assistant=left grey, user=right dark)
- [ ] Tool call display cards (collapsible, monospace)
- [ ] Inline data cards in responses (with severity left-border)
- [ ] Suggested query chips (clickable)
- [ ] Thinking/typing indicator (animated dots)
- [ ] Chat input with send button
- [ ] SSE (EventSource) connection for streaming agent responses
- [ ] Message history within session
- [ ] "Ask SENTRY AI" button in expanded row links to chat with pre-filled context

## Phase 2: Tier 2 SQL Analyst (Weeks 7-10)

### 2.1 Tier 2 Constrained SQL
- [ ] Implement ConstrainedSQLExecutor with all guardrails
- [ ] Auto-discover schema via LangChain SQLDatabase at startup
- [ ] Build domain_rules.py with static rules (TRIGGER_TYPE, DAG_RUN_ID format, etc.)
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
