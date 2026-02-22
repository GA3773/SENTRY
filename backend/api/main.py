"""FastAPI application for SENTRY — SRE Intelligent Batch Monitoring Platform."""

import asyncio
import json
import logging
import os
import uuid
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = FastAPI(title="SENTRY", description="SRE Intelligent Batch Monitoring Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Frontend: Jinja2 templates + static files served by FastAPI
# ---------------------------------------------------------------------------

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

app.mount("/static", StaticFiles(directory=str(_frontend_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_frontend_dir / "templates"))


# ---------------------------------------------------------------------------
# Module-level services and mappings
# ---------------------------------------------------------------------------

_lenz_service = None


def _get_lenz_service():
    global _lenz_service
    if _lenz_service is None:
        from services.lenz_service import LenzService

        _lenz_service = LenzService()
    return _lenz_service


# Lenz essential name → UI display name
_DISPLAY_NAMES: dict[str, str] = {
    "6G-FR2052a-E2E": "FR2052A (6G)",
    "PBSynthetics": "PBSynthetics",
    "SNU": "SNU",
    "SNU-Strategic": "SNU Strategic",
    "SNU-REG-STRATEGIC": "SNU REG Strategic",
    "TB-Collateral": "COLLATERAL",
    "TB-Derivatives": "DERIVATIVES",
    "TB-Securities": "SECURITIES",
    "TB-SecFIn": "SECFIN",
    "TB-CFG": "CFG",
    "TB-SMAA": "SMAA",
    "UPC": "UPC",
}


@app.get("/")
async def dashboard(request: Request):
    """Serve the main dashboard page via Jinja2 template."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    business_date: str | None = None
    processing_type: str | None = None


class ChatResponseData(BaseModel):
    text: str
    structured_data: dict | None = None
    tool_calls: list[dict] = []
    suggested_queries: list[str] = []
    error: bool = False


class ChatResponse(BaseModel):
    thread_id: str
    response: ChatResponseData


# ---------------------------------------------------------------------------
# POST /api/chat — main conversational endpoint
# ---------------------------------------------------------------------------


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Run the SENTRY LangGraph agent for a user message.

    A fresh LLM client is created per invocation (create_llm() inside nodes)
    to ensure a fresh Bearer token.
    """
    from agent.graph import sentry_graph

    # Only set fields explicitly provided by the API caller.
    # Omitted fields retain their previous values from the MemorySaver checkpoint,
    # enabling follow-up questions without re-specifying batch/date context.
    input_state: dict = {
        "messages": [HumanMessage(content=req.message)],
    }
    if req.business_date:
        input_state["business_date"] = req.business_date
    if req.processing_type:
        input_state["processing_type"] = req.processing_type

    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        result = await asyncio.to_thread(sentry_graph.invoke, input_state, config)
    except Exception as e:
        log.error("Graph invocation failed: %s", e, exc_info=True)
        return ChatResponse(
            thread_id=req.thread_id,
            response=ChatResponseData(
                text=f"I encountered an error processing your request: {e}",
                error=True,
            ),
        )

    return ChatResponse(
        thread_id=req.thread_id,
        response=ChatResponseData(
            text=result.get("response_text", "No response generated."),
            structured_data=result.get("structured_data"),
            tool_calls=result.get("tool_calls_log") or [],
            suggested_queries=result.get("suggested_queries") or [],
            error=bool(result.get("error")),
        ),
    )


# ---------------------------------------------------------------------------
# GET /api/chat/stream — SSE streaming endpoint
# ---------------------------------------------------------------------------


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream agent node transitions as Server-Sent Events.

    Each SSE event carries a JSON payload describing node starts/ends
    and the final response.
    """
    from agent.graph import sentry_graph

    input_state: dict = {
        "messages": [HumanMessage(content=req.message)],
    }
    if req.business_date:
        input_state["business_date"] = req.business_date
    if req.processing_type:
        input_state["processing_type"] = req.processing_type

    config = {"configurable": {"thread_id": req.thread_id}}

    async def event_generator():
        try:
            # Use stream_mode to get node-level events
            for event in sentry_graph.stream(input_state, config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    # Node start
                    yield {
                        "data": json.dumps(
                            {"type": "node_start", "node": node_name},
                            default=str,
                        )
                    }

                    # Emit tool calls if this node added any
                    tool_calls = node_output.get("tool_calls_log") or []
                    for tc in tool_calls:
                        yield {
                            "data": json.dumps(
                                {
                                    "type": "tool_call",
                                    "tool": tc.get("tool"),
                                    "status": "completed",
                                    "duration_ms": tc.get("duration_ms"),
                                },
                                default=str,
                            )
                        }

                    # Node end with summary
                    result_summary = {}
                    if node_name == "intent_classifier":
                        result_summary = {"intent": node_output.get("intent")}
                    elif node_name == "batch_resolver":
                        result_summary = {
                            "batch": node_output.get("batch_name"),
                            "dataset_count": len(node_output.get("dataset_ids") or []),
                        }
                    elif node_name == "data_fetcher":
                        bs = (node_output.get("query_results") or {}).get(
                            "batch_status", {}
                        )
                        result_summary = {"row_count": bs.get("total", 0)}
                    elif node_name == "response_synthesizer":
                        # Final response — send as "response" event
                        yield {
                            "data": json.dumps(
                                {
                                    "type": "response",
                                    "data": {
                                        "text": node_output.get("response_text", ""),
                                        "structured_data": node_output.get(
                                            "structured_data"
                                        ),
                                        "tool_calls": node_output.get("tool_calls_log")
                                        or [],
                                        "suggested_queries": node_output.get(
                                            "suggested_queries"
                                        )
                                        or [],
                                    },
                                },
                                default=str,
                            )
                        }

                    yield {
                        "data": json.dumps(
                            {
                                "type": "node_end",
                                "node": node_name,
                                "result": result_summary,
                            },
                            default=str,
                        )
                    }

            yield {"data": "[DONE]"}

        except Exception as e:
            log.error("SSE stream error: %s", e, exc_info=True)
            yield {
                "data": json.dumps(
                    {
                        "type": "response",
                        "data": {
                            "text": f"Stream error: {e}",
                            "error": True,
                        },
                    }
                )
            }
            yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# GET /api/essentials — all essentials with live status
# ---------------------------------------------------------------------------


def _fmt_dt(val) -> str | None:
    """Format a datetime to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat() + "Z"
    return str(val)


def _calc_duration(row: dict | None) -> int:
    """Calculate duration in minutes from a DB row's CREATED_DATE → UPDATED_DATE."""
    if not row:
        return 0
    created = row.get("CREATED_DATE")
    updated = row.get("UPDATED_DATE")
    if not created or not updated:
        return 0
    try:
        if isinstance(created, datetime) and isinstance(updated, datetime):
            return max(0, int((updated - created).total_seconds() / 60))
    except Exception:
        pass
    return 0


def _agg_processing_type(
    rows_by_ds: dict[str, dict], all_dataset_ids: list[str]
) -> dict:
    """Aggregate status for one processing type (PRELIM or FINAL)."""
    total = len(all_dataset_ids)
    success = 0
    failed = 0
    running = 0
    not_started = 0
    earliest_created = None
    latest_updated = None

    for ds_id in all_dataset_ids:
        row = rows_by_ds.get(ds_id)
        if not row:
            not_started += 1
            continue
        status = row.get("STATUS", "UNKNOWN")
        if status == "SUCCESS":
            success += 1
        elif status in ("FAILED", "CANCELLED"):
            failed += 1
        elif status in ("RUNNING", "QUEUED"):
            running += 1
        else:
            not_started += 1

        created = row.get("CREATED_DATE")
        updated = row.get("UPDATED_DATE")
        if created and (earliest_created is None or created < earliest_created):
            earliest_created = created
        if updated and (latest_updated is None or updated > latest_updated):
            latest_updated = updated

    if total == 0:
        proc_status = "NOT_STARTED"
    elif failed > 0:
        proc_status = "PARTIAL_FAILURE" if success > 0 else "FAILED"
    elif running > 0:
        proc_status = "RUNNING"
    elif success == total:
        proc_status = "SUCCESS"
    elif success > 0:
        proc_status = "RUNNING"
    else:
        proc_status = "NOT_STARTED"

    return {
        "status": proc_status,
        "total_datasets": total,
        "success": success,
        "failed": failed,
        "running": running,
        "not_started": not_started,
        "progress": f"{success}/{total}",
        "started_at": _fmt_dt(earliest_created),
        "last_updated": _fmt_dt(latest_updated),
        "eta": None,
    }


def _compute_overall_status(prelim: dict, final: dict) -> str:
    """Compute essential-level status from prelim + final aggregations."""
    p = prelim["status"]
    f = final["status"]

    if p in ("FAILED", "PARTIAL_FAILURE") or f in ("FAILED", "PARTIAL_FAILURE"):
        has_success = prelim["success"] > 0 or final["success"] > 0
        return "PARTIAL_FAILURE" if has_success else "FAILED"
    if p == "RUNNING" or f == "RUNNING":
        return "RUNNING"
    if p == "SUCCESS" and f == "SUCCESS":
        return "SUCCESS"
    if p == "SUCCESS" and f == "NOT_STARTED":
        return "SUCCESS"
    if p == "NOT_STARTED" and f == "NOT_STARTED":
        return "NOT_STARTED"
    return "RUNNING"


def _build_essential_status(
    essential_name: str,
    definition,
    business_date: str,
) -> dict | None:
    """Build status for a single essential (sync — called from thread)."""
    from agent.tools.batch_tools import get_batch_status

    dataset_ids = definition.dataset_ids
    if not dataset_ids:
        return None

    result = get_batch_status(dataset_ids, business_date)
    rows = result.get("rows", [])

    # Index by (dataset_id, processing_type)
    prelim_by_ds: dict[str, dict] = {}
    final_by_ds: dict[str, dict] = {}
    for row in rows:
        ds_id = row.get("OUTPUT_DATASET_ID", "")
        proc = row.get("processing_type", "")
        if proc == "PRELIM":
            prelim_by_ds[ds_id] = row
        elif proc == "FINAL":
            final_by_ds[ds_id] = row

    prelim_info = _agg_processing_type(prelim_by_ds, dataset_ids)
    final_info = _agg_processing_type(final_by_ds, dataset_ids)

    datasets_detail = []
    for ds in definition.datasets:
        ds_id = ds.dataset_id
        p_row = prelim_by_ds.get(ds_id)
        f_row = final_by_ds.get(ds_id)
        p_status = p_row["STATUS"] if p_row else "NOT_STARTED"
        f_status = f_row["STATUS"] if f_row else "NOT_STARTED"
        latest_row = p_row or f_row
        slice_count = len(ds.all_slices) if ds.slice_groups else 0

        datasets_detail.append(
            {
                "dataset_id": ds_id,
                "sequence_order": ds.sequence_order,
                "prelim_status": p_status,
                "final_status": f_status,
                "slice_count": slice_count,
                "slices_success": slice_count if p_status == "SUCCESS" else 0,
                "slices_failed": slice_count if p_status == "FAILED" else 0,
                "latest_dag_run_id": (latest_row or {}).get("DAG_RUN_ID", ""),
                "duration_minutes": _calc_duration(latest_row),
                "created_date": _fmt_dt(
                    (latest_row or {}).get("CREATED_DATE")
                ),
                "updated_date": _fmt_dt(
                    (latest_row or {}).get("UPDATED_DATE")
                ),
            }
        )

    overall = _compute_overall_status(prelim_info, final_info)

    return {
        "essential_name": essential_name,
        "display_name": _DISPLAY_NAMES.get(essential_name, essential_name),
        "status": overall,
        "prelim": prelim_info,
        "final": final_info,
        "datasets": datasets_detail,
    }


def _build_essentials_response(business_date: str) -> dict:
    """Build the full GET /api/essentials response (sync, runs in thread)."""
    from config.essentials_map import ESSENTIAL_MAP

    lenz = _get_lenz_service()
    unique_essentials = sorted(set(ESSENTIAL_MAP.values()))

    essentials_list: list[dict] = []
    summary = {
        "total": 0,
        "completed": 0,
        "running": 0,
        "failed": 0,
        "not_started": 0,
    }

    for ess_name in unique_essentials:
        try:
            defn = lenz.get_essential_definition(ess_name)
        except Exception as e:
            log.warning("Skipping %s: %s", ess_name, e)
            continue

        ess_obj = _build_essential_status(ess_name, defn, business_date)
        if not ess_obj:
            continue

        essentials_list.append(ess_obj)
        summary["total"] += 1
        st = ess_obj["status"]
        if st == "SUCCESS":
            summary["completed"] += 1
        elif st == "RUNNING":
            summary["running"] += 1
        elif st in ("FAILED", "PARTIAL_FAILURE"):
            summary["failed"] += 1
        else:
            summary["not_started"] += 1

    return {
        "business_date": business_date,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "essentials": essentials_list,
    }


@app.get("/api/essentials")
async def get_essentials(
    business_date: str | None = None,
    processing_type: str | None = None,
):
    """Return current status of ALL monitored essentials for the dashboard."""
    bdate = business_date or date.today().isoformat()
    return await asyncio.to_thread(_build_essentials_response, bdate)


# ---------------------------------------------------------------------------
# GET /api/status/{essential_name} — single essential status
# ---------------------------------------------------------------------------


@app.get("/api/status/{essential_name}")
async def get_essential_status(
    essential_name: str,
    business_date: str | None = None,
    processing_type: str | None = None,
):
    """Return status for a single essential (bypasses agent)."""
    from services.lenz_service import resolve_essential_name

    bdate = business_date or date.today().isoformat()
    resolved = resolve_essential_name(essential_name)
    if not resolved:
        return {"error": f"Unknown essential: {essential_name}"}

    lenz = _get_lenz_service()

    def _build():
        defn = lenz.get_essential_definition(resolved)
        return _build_essential_status(resolved, defn, bdate)

    result = await asyncio.to_thread(_build)
    if not result:
        return {"error": f"No data for {essential_name}"}
    return result


# ---------------------------------------------------------------------------
# GET /api/lenz/refresh — force-refresh Lenz cache
# ---------------------------------------------------------------------------


@app.get("/api/lenz/refresh")
async def lenz_refresh():
    """Force-refresh Lenz API cache for all essentials."""
    lenz = _get_lenz_service()

    def _refresh():
        lenz.invalidate()
        lenz.prefetch_all()
        return list(lenz._cache.keys())

    refreshed = await asyncio.to_thread(_refresh)
    return {
        "refreshed": refreshed,
        "failed": [],
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Startup event — prefetch Lenz definitions
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_prefetch():
    """Pre-fetch Lenz definitions on server start."""
    try:
        lenz = _get_lenz_service()
        await asyncio.to_thread(lenz.prefetch_all)
        log.info("Lenz prefetch completed")
    except Exception as e:
        log.warning("Lenz prefetch failed (will fetch on demand): %s", e)


# ---------------------------------------------------------------------------
# GET /api/health — connectivity checks
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health_check() -> dict:
    """Health check with connectivity status for all external dependencies."""
    checks: dict[str, str] = {}
    errors: list[str] = []
    now = datetime.utcnow().isoformat() + "Z"

    # Check FGW database
    try:
        from services.db_service import get_fgw_engine
        from sqlalchemy import text

        engine = get_fgw_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["fgw_database"] = "connected"
    except Exception as e:
        checks["fgw_database"] = "error"
        errors.append(f"fgw_database: {e}")

    # Check Airflow database
    try:
        from services.db_service import get_airflow_engine
        from sqlalchemy import text

        engine = get_airflow_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["airflow_database"] = "connected"
    except Exception as e:
        checks["airflow_database"] = "error"
        errors.append(f"airflow_database: {e}")

    # Check Lenz API reachability
    try:
        lenz_url = os.getenv("LENZ_API_BASE_URL")
        if lenz_url:
            checks["lenz_api"] = "configured"
        else:
            checks["lenz_api"] = "not_configured"
            errors.append("lenz_api: LENZ_API_BASE_URL not set")
    except Exception as e:
        checks["lenz_api"] = "error"
        errors.append(f"lenz_api: {e}")

    # Check Azure OpenAI configuration
    try:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if endpoint and api_key:
            checks["azure_openai"] = "configured"
        else:
            checks["azure_openai"] = "not_configured"
            errors.append("azure_openai: AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY not set")
    except Exception as e:
        checks["azure_openai"] = "error"
        errors.append(f"azure_openai: {e}")

    status = "ok" if not errors else "degraded"
    result: dict = {"status": status, "checks": checks, "timestamp": now}
    if errors:
        result["errors"] = errors

    return result
