"""FastAPI application for SENTRY — SRE Intelligent Batch Monitoring Platform."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
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
