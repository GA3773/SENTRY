"""Response synthesizer node — uses the LLM to generate natural language summaries."""

import json
import logging
from datetime import date

from langchain_core.messages import AIMessage, SystemMessage

from agent.state import SentryState
from services.azure_openai import create_llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are SENTRY, an intelligent SRE assistant for batch monitoring at JPMorgan Chase.

Generate a concise, informative response about batch processing status. \
Be direct and factual — SRE teams need actionable information, not filler.

## Guidelines
- Lead with the most important information (failures, blockers)
- Use specific numbers: "3 of 6 datasets succeeded" not "some datasets succeeded"
- Reference sequence order when relevant: "Step 3 (sequence order 2) is blocked"
- Include dataset IDs for failed items so SREs can investigate
- Duration in minutes unless > 120 min, then use hours
- If there are failures AND you have task-level details, mention the specific failed tasks
- Keep it under 200 words unless the user asked for details

## Response Structure
Return ONLY valid JSON:
{{
  "text": "<natural language summary>",
  "suggested_queries": ["<follow-up 1>", "<follow-up 2>", "<follow-up 3>"]
}}
"""


def response_synthesizer(state: SentryState) -> dict:
    """Generate the final natural language response using the LLM.

    Handles all intents including error states and short-circuits
    (prediction placeholder, out_of_scope).
    """
    intent = state.get("intent", "out_of_scope")
    error = state.get("error")

    # Short-circuit: prediction placeholder (set by intent_classifier)
    if intent == "prediction" and state.get("response_text"):
        return _build_response(
            text=state["response_text"],
            suggested_queries=state.get("suggested_queries", []),
            state=state,
        )

    # Short-circuit: error state
    if error:
        return _build_response(
            text=f"I ran into an issue: {error}",
            suggested_queries=_error_suggestions(state),
            state=state,
        )

    # Short-circuit: out_of_scope
    if intent == "out_of_scope":
        return _build_response(
            text=(
                "I'm SENTRY, a batch monitoring assistant. I can help with:\n"
                "- Checking batch/essential status\n"
                "- Investigating failures (RCA)\n"
                "- Viewing task-level details for specific DAG runs\n\n"
                "Try asking about a specific batch like Derivatives, 6G, or SNU."
            ),
            suggested_queries=[
                "How is derivatives doing today?",
                "What is the status of 6G?",
                "Show me SNU status",
            ],
            state=state,
        )

    # Normal flow: use LLM to synthesize response from analysis
    context = _build_context(state)

    try:
        llm = create_llm()
        llm_response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            SystemMessage(content=f"Context:\n{context}"),
        ])
        raw = llm_response.content.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
        text = parsed.get("text", raw)
        suggested = parsed.get("suggested_queries", [])
    except json.JSONDecodeError:
        log.warning("Response synthesizer returned non-JSON, using raw text")
        text = raw
        suggested = _default_suggestions(state)
    except Exception as e:
        log.error("Response synthesizer LLM call failed: %s", e)
        text = _fallback_text(state)
        suggested = _default_suggestions(state)

    # Build structured_data for the UI based on intent
    structured_data = _build_structured_data(state)

    return _build_response(
        text=text,
        suggested_queries=suggested,
        state=state,
        structured_data=structured_data,
    )


def _build_response(
    text: str,
    suggested_queries: list[str],
    state: SentryState,
    structured_data: dict | None = None,
) -> dict:
    """Assemble the final state update with an AIMessage for conversation memory."""
    return {
        "messages": [AIMessage(content=text)],
        "response_text": text,
        "structured_data": structured_data,
        "suggested_queries": suggested_queries[:5],
    }


def _build_context(state: SentryState) -> str:
    """Build a context string for the LLM from accumulated state."""
    parts = []

    parts.append(f"Intent: {state.get('intent')}")
    parts.append(f"Batch: {state.get('batch_name', 'unknown')}")
    parts.append(f"Business Date: {state.get('business_date', date.today().isoformat())}")

    pt = state.get("processing_type")
    if pt:
        parts.append(f"Processing Type: {pt}")

    analysis = state.get("analysis")
    if analysis:
        parts.append(f"\nAnalysis:\n{json.dumps(analysis, indent=2, default=str)}")

    query_results = state.get("query_results")
    if query_results:
        # Include task details if present
        task_details = query_results.get("task_details")
        if task_details:
            parts.append(f"\nTask Details:\n{json.dumps(task_details, indent=2, default=str)}")

    rca = state.get("rca_findings")
    if rca and rca.get("failed_datasets"):
        parts.append(f"\nRCA Findings:\n{json.dumps(rca, indent=2, default=str)}")

    return "\n".join(parts)


def _build_structured_data(state: SentryState) -> dict | None:
    """Build the structured_data object for the API response."""
    intent = state.get("intent")
    analysis = state.get("analysis")
    if not analysis:
        return None

    if intent in ("status_check", "rca_drilldown"):
        data: dict = {
            "type": "batch_status" if intent == "status_check" else "rca_analysis",
            "batch_name": state.get("batch_name"),
            "business_date": state.get("business_date"),
            "processing_type": state.get("processing_type"),
            "summary": analysis.get("summary"),
        }
        if analysis.get("sequence_progress"):
            data["sequence_progress"] = analysis["sequence_progress"]
        if analysis.get("failures"):
            data["failures"] = analysis["failures"]
        return data

    if intent == "task_detail":
        qr = state.get("query_results") or {}
        return {
            "type": "task_details",
            "dag_run_id": qr.get("dag_run_id"),
            "tasks": qr.get("task_details", {}).get("tasks", []),
            "summary": qr.get("task_details", {}).get("summary", {}),
        }

    return None


def _fallback_text(state: SentryState) -> str:
    """Generate a basic text response when the LLM is unavailable."""
    analysis = state.get("analysis") or {}
    summary = analysis.get("summary", {})
    batch = state.get("batch_name", "the batch")
    bdate = state.get("business_date", "today")

    if summary:
        return (
            f"{batch} for {bdate}: "
            f"{summary.get('success', 0)} succeeded, "
            f"{summary.get('failed', 0)} failed, "
            f"{summary.get('running', 0)} running, "
            f"{summary.get('not_started', 0)} not started "
            f"(out of {summary.get('total_datasets', 0)} total datasets)."
        )
    return f"Retrieved data for {batch} on {bdate}. See structured_data for details."


def _default_suggestions(state: SentryState) -> list[str]:
    """Generate default suggested queries based on context."""
    batch = state.get("batch_name")
    suggestions = []
    if batch:
        suggestions.append(f"What failed in {batch}?")
        suggestions.append(f"Show me the task details for the failed run")
        suggestions.append(f"How long did {batch} take last week?")
    else:
        suggestions.append("How is derivatives doing today?")
        suggestions.append("What is the status of 6G?")
    return suggestions


def _error_suggestions(state: SentryState) -> list[str]:
    """Suggestions when an error occurred."""
    return [
        "Try asking about a specific batch: derivatives, 6G, SNU",
        "What batches can you monitor?",
    ]
