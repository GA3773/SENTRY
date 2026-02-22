"""LangGraph state machine for the SENTRY agent.

Defines the full agent workflow with conditional routing based on intent:

  START → context_loader → intent_classifier
    → status_check    → batch_resolver → data_fetcher → analyzer → response_synthesizer → END
    → rca_drilldown   → batch_resolver → data_fetcher → analyzer → response_synthesizer → END
    → task_detail     → data_fetcher → response_synthesizer → END
    → general_query   → batch_resolver → response_synthesizer → END (Tier 2 future)
    → prediction      → response_synthesizer → END
    → out_of_scope    → response_synthesizer → END

context_loader clears stale per-turn fields (error, response_text, analysis, etc.)
while MemorySaver preserves conversation context (batch_name, dataset_ids, etc.).

Error short-circuit: if any node sets state["error"], routing skips to response_synthesizer.
"""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agent.nodes.analyzer import analyzer
from agent.nodes.batch_resolver import batch_resolver
from agent.nodes.context_loader import context_loader
from agent.nodes.data_fetcher import data_fetcher
from agent.nodes.intent_classifier import intent_classifier
from agent.nodes.response_synthesizer import response_synthesizer
from agent.state import SentryState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------

def route_after_intent(state: SentryState) -> str:
    """Route from intent_classifier to the next node based on classified intent."""
    if state.get("error"):
        return "response_synthesizer"

    intent = state.get("intent", "out_of_scope")

    if intent in ("status_check", "rca_drilldown", "general_query"):
        return "batch_resolver"
    elif intent == "task_detail":
        return "data_fetcher"
    else:
        # prediction, out_of_scope, or unknown
        return "response_synthesizer"


def route_after_resolver(state: SentryState) -> str:
    """Route from batch_resolver based on intent (and error state)."""
    if state.get("error"):
        return "response_synthesizer"

    intent = state.get("intent", "general_query")

    if intent in ("status_check", "rca_drilldown"):
        return "data_fetcher"
    else:
        # general_query → straight to response (Tier 2 SQL not yet implemented)
        return "response_synthesizer"


def route_after_fetcher(state: SentryState) -> str:
    """Route from data_fetcher based on intent."""
    if state.get("error"):
        return "response_synthesizer"

    intent = state.get("intent", "status_check")

    if intent in ("status_check", "rca_drilldown"):
        return "analyzer"
    else:
        # task_detail → skip analyzer, go straight to response
        return "response_synthesizer"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Build and return the compiled SENTRY LangGraph with MemorySaver."""
    workflow = StateGraph(SentryState)

    # Register nodes
    workflow.add_node("context_loader", context_loader)
    workflow.add_node("intent_classifier", intent_classifier)
    workflow.add_node("batch_resolver", batch_resolver)
    workflow.add_node("data_fetcher", data_fetcher)
    workflow.add_node("analyzer", analyzer)
    workflow.add_node("response_synthesizer", response_synthesizer)

    # Entry point — context_loader runs first to clear stale per-turn fields
    workflow.set_entry_point("context_loader")

    # context_loader always flows to intent_classifier
    workflow.add_edge("context_loader", "intent_classifier")

    # Conditional edges
    workflow.add_conditional_edges(
        "intent_classifier",
        route_after_intent,
        {
            "batch_resolver": "batch_resolver",
            "data_fetcher": "data_fetcher",
            "response_synthesizer": "response_synthesizer",
        },
    )

    workflow.add_conditional_edges(
        "batch_resolver",
        route_after_resolver,
        {
            "data_fetcher": "data_fetcher",
            "response_synthesizer": "response_synthesizer",
        },
    )

    workflow.add_conditional_edges(
        "data_fetcher",
        route_after_fetcher,
        {
            "analyzer": "analyzer",
            "response_synthesizer": "response_synthesizer",
        },
    )

    # Fixed edges
    workflow.add_edge("analyzer", "response_synthesizer")
    workflow.add_edge("response_synthesizer", END)

    # Compile with in-memory checkpointer for session persistence
    checkpointer = MemorySaver()
    graph = workflow.compile(checkpointer=checkpointer)

    log.info("SENTRY LangGraph compiled successfully")
    return graph


# Module-level compiled graph — reused across all requests.
# MemorySaver state persists in-memory within this process.
sentry_graph = build_graph()
