# SENTRY

**SRE Intelligent Batch Monitoring Platform** — LLM-powered agentic platform for monitoring batch processing workflows at JPMorgan Chase.

## Quick Start for Claude Code

1. Read `CLAUDE_CODE_INSTRUCTIONS.md` — follow it session by session
2. `CLAUDE.md` is auto-loaded every session by Claude Code
3. Reference `docs/` files with `@docs/filename.md` when you need details
4. Open `docs/ui-reference.html` in a browser — this is the exact UI to build

## Documentation Map

| File | Purpose | When to reference |
|------|---------|-------------------|
| `CLAUDE_CODE_INSTRUCTIONS.md` | Step-by-step session prompts for Claude Code | Follow this to build SENTRY |
| `CLAUDE.md` | Project overview, tech stack, critical rules, code style | Every session (auto-loaded) |
| `docs/architecture.md` | Full system architecture, LangGraph design, layer details | Building agent, understanding flow |
| `docs/data-model.md` | Database schemas, column semantics, sample data, query patterns | Writing ANY database query |
| `docs/lenz-integration.md` | Lenz API details, response parsing, caching, Pydantic models | Building batch resolver, Lenz service |
| `docs/query-tier-system.md` | Tier 1/2/3 query architecture, tool definitions, SQL guardrails | Building tools, query execution |
| `docs/connectivity.md` | RDS, Azure OpenAI, Lenz, AWS connection patterns | Setting up connections |
| `docs/api-contracts.md` | API endpoint request/response JSON shapes | Building frontend, connecting to backend |
| `docs/ui-design.md` | Complete design system tokens, component specs | Building ANY UI component |
| `docs/ui-reference.html` | Working HTML mockup — THE visual reference | Building UI (open in browser) |
| `docs/implementation-plan.md` | Phased plan with checkboxes | Task tracking, knowing what to build next |

## Key Principle

**Never assume batch→dataset mappings.** A batch ("Essential") is an arbitrary grouping of datasets with no naming pattern. ALWAYS resolve through Lenz API.
