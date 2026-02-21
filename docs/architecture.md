# SENTRY Architecture Document

## System Architecture Overview

SENTRY is a multi-layer agentic AI platform. It is NOT a simple chatbot — it is a stateful, tool-calling agent built on LangGraph that reasons over batch processing state by querying multiple data sources.

## Architecture Layers

### Layer 1: Data Access Layer (DAL)
Pre-built, parameterized query functions the agent invokes as tools. The LLM picks tools and fills parameters — it does NOT write raw SQL for standard queries.

**Why parameterized over raw SQL:**
- Query cost control (LIMIT guards, index hints, timeouts)
- Security (no injection risk, no accidental writes)
- Reliability (pre-tested queries, deterministic schema-quirk handling)
- Speed (no SQL generation latency for common queries)

### Layer 2: Batch Configuration (Lenz API)
The Lenz API at `lenz-app.prod.aws.jpmchase.net/lenz/essentials/def?name={essential_name}` is the SINGLE SOURCE OF TRUTH for:
- Which datasets belong to a batch
- Execution sequence order (sequenceOrder field)
- Valid slices per dataset (sliceGroups)

See @docs/lenz-integration.md for full details.

**CRITICAL**: There is NO static YAML config for batch definitions. Lenz API is called (with caching) for every batch resolution. A batch is an ARBITRARY grouping of datasets — dataset IDs do NOT follow naming patterns.

### Layer 3: Agent Orchestration (LangGraph)
Stateful multi-step agent with conditional routing.

#### LangGraph State Definition
```python
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages

class SentryState(TypedDict):
    messages: Annotated[list, add_messages]  # Chat history
    intent: Optional[str]                     # Classified intent
    batch_name: Optional[str]                 # Resolved batch name
    batch_definition: Optional[dict]          # Lenz API response (cached)
    dataset_ids: Optional[List[str]]          # Resolved dataset IDs
    business_date: Optional[str]              # Target date
    processing_type: Optional[str]            # PRELIM, FINAL, or None
    query_results: Optional[dict]             # Results from DAL
    rca_findings: Optional[dict]              # RCA analysis results
    error: Optional[str]                      # Error state
```

#### LangGraph Nodes

1. **intent_classifier** — Determines user intent:
   - `status_check`: "How is derivatives doing?"
   - `rca_drilldown`: "What failed in 6G?"
   - `task_detail`: "Show me the tasks for this dag run"
   - `prediction`: "When will COLLATERAL finish?" **(Phase 3 — returns placeholder message until implemented)**
   - `general_query`: Analytical/ad-hoc questions (Tier 2)
   - `out_of_scope`: Non-batch questions

2. **batch_resolver** — Resolves natural language → Lenz essential name → API call → dataset IDs + sequences + slices. Uses the ESSENTIAL_MAP from config. ALWAYS called before any database query.

3. **data_fetcher** — Executes Tier 1 parameterized tools against RDS.

4. **sql_analyst** — Tier 2: LLM-generated SQL for novel analytical questions. Sandboxed with read-only connection, 10s timeout, LIMIT injection, AST validation.

5. **analyzer** — Reasons over fetched data:
   - Groups results by sequence order (from Lenz)
   - Identifies failures, partial completions
   - Computes progress ("step 3 of 6")
   - Detects anomalies (duration outliers)

6. **response_synthesizer** — Formats final response with:
   - Natural language summary
   - Structured data cards (for UI rendering)
   - Suggested follow-up queries

#### LangGraph Edges (Conditional Routing)

```
START → intent_classifier

intent_classifier:
  → status_check    → batch_resolver → data_fetcher → analyzer → response_synthesizer
  → rca_drilldown   → batch_resolver → data_fetcher → analyzer → response_synthesizer
  → task_detail     → data_fetcher → response_synthesizer
  → prediction      → response_synthesizer (placeholder: "Coming in Phase 3")
  → general_query   → batch_resolver → sql_analyst → response_synthesizer
  → out_of_scope    → response_synthesizer
```

### Layer 4: Memory & Context

**Short-term (session):** LangGraph's built-in `MemorySaver` (in-memory checkpointing). Keeps conversational thread alive ("we were talking about DERIVATIVES for 2026-02-13") across turns within a session. This is sufficient for Phase 1 (single-process, local deployment). Upgrade to `RedisSaver` in Phase 4 when multi-process/multi-user support is needed.

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

# Each conversation gets a unique thread_id
result = graph.invoke(
    {"messages": [{"role": "user", "content": user_message}]},
    config={"configurable": {"thread_id": thread_id}}
)
```

**Note:** MemorySaver state is lost on process restart. This is acceptable for Phase 1. Session persistence across restarts is a Phase 4 requirement (Redis or PostgreSQL-backed checkpointer).

**Long-term (operational — Phase 3+):** Not part of current implementation. Future phases will add persistent storage for:
- Historical batch runtimes per dataset/slice (for prediction)
- Past RCA findings (for pattern matching)
- Query audit log (every tool call, SQL executed, results returned)

Storage backend TBD (PostgreSQL, SQLite, or a dedicated analytics table in existing RDS).

### Layer 5: Interface

**Backend API:** FastAPI with SSE (Server-Sent Events) support for streaming agent responses.
**Frontend:** React + TypeScript following LRI-Labs design system.
**Future:** Slack bot, PagerDuty webhook integration, Grafana panel embedding.

## Query Tier System

See @docs/query-tier-system.md for full details.

- **Tier 1 (80% of queries)**: Parameterized tools with flexible optional parameters. Fast, reliable, no LLM SQL.
- **Tier 2 (15% of queries)**: Constrained LLM SQL generation. Schema auto-discovered via LangChain SQLDatabase + domain rules + few-shot examples from vector store. Sandboxed execution.
- **Tier 3 (5% of queries)**: Graceful decline for out-of-scope questions.

## Security & Guardrails

- All database connections are READ-ONLY
- Query timeout: 10 seconds max
- Row limit: 500 rows max, injected if LLM forgets
- SQL AST validation: only SELECT allowed, whitelist of tables
- Lenz API cache TTL: 300 seconds (5 minutes)
- All agent traces logged for audit (LangSmith/LangFuse)
- No LLM-generated SQL for Tier 1 — parameterized queries only

## Phased Implementation

See @docs/implementation-plan.md for detailed plan with checkboxes.
- Phase 1: Status reporting + basic RCA (Tier 1 tools, Lenz integration, Chat UI)
- Phase 2: Tier 2 SQL analyst
- Phase 3: Runtime prediction + historical data pipeline
- Phase 4: AWS diagnostics (CloudWatch, SQS — resource names TBD)
- Phase 5: Proactive monitoring, alerting, Slack, RBAC, EKS deployment
