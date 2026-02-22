"""Intent classifier node — uses the LLM to determine user intent."""

import json
import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from agent.state import SentryState
from services.azure_openai import create_llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the intent classifier for SENTRY, an SRE batch monitoring platform \
that tracks batch processing workflows ("Essentials" / "Asset Classes").

Given the user's message (and any prior conversation context), classify it \
into EXACTLY ONE intent and extract relevant entities.

## Intents

- **status_check** — User wants overall status of a batch/essential.
  Examples: "How is derivatives doing?", "What's the status of 6G?", "Is SNU complete?"

- **rca_drilldown** — User wants to investigate failures or errors.
  Examples: "What failed in derivatives?", "Why did 6G fail?", "Show me errors in SNU"

- **task_detail** — User wants task-level details for a specific DAG run.
  Examples: "Show me the tasks for this dag run", "What tasks failed?"

- **prediction** — User wants to predict when a batch will finish.
  Examples: "When will derivatives finish?", "ETA for 6G?"

- **general_query** — Analytical or ad-hoc questions about data / history.
  Examples: "How long did derivatives take last week?", "Compare today vs yesterday"

- **out_of_scope** — Not related to batch monitoring.
  Examples: "What's the weather?", "Tell me a joke"

## Entity Extraction

Extract these entities if present in the message (or carried from prior context):

- **batch_name**: The batch / essential / asset class mentioned (e.g. "derivatives", \
"6G", "SNU", "collateral"). Use the raw user term, not the Lenz name.
- **business_date**: A date reference like "today", "yesterday", "2026-02-21". \
Convert relative dates using today = {today}.
- **processing_type**: "PRELIM" or "FINAL" if explicitly mentioned, else null.
- **slice_ref**: A slice reference if mentioned (e.g. "EMEA", "NA", "APAC").

## Response Format

Return ONLY valid JSON — no markdown, no explanation:
{{
  "intent": "<one of the intents above>",
  "batch_name": "<string or null>",
  "business_date": "<YYYY-MM-DD or null>",
  "processing_type": "<PRELIM|FINAL or null>",
  "slice_ref": "<string or null>"
}}
"""


def intent_classifier(state: SentryState) -> dict:
    """Classify the user's intent and extract entities from their message."""
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "out_of_scope", "error": "No message provided"}

    today = state.get("business_date") or date.today().isoformat()
    prompt = SYSTEM_PROMPT.replace("{today}", today)

    try:
        llm = create_llm()
        llm_messages = [SystemMessage(content=prompt)] + messages
        response = llm.invoke(llm_messages)
        raw = response.content.strip()

        # Strip markdown fences if the LLM wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Intent classifier returned non-JSON: %s", raw)
        return {"intent": "out_of_scope", "error": f"Failed to parse intent: {raw}"}
    except Exception as e:
        log.error("Intent classifier LLM call failed: %s", e)
        return {"intent": "out_of_scope", "error": str(e)}

    intent = parsed.get("intent", "out_of_scope")
    log.info("Classified intent: %s", intent)

    updates: dict = {
        "intent": intent,
        "tool_calls_log": state.get("tool_calls_log") or [],
    }

    # Populate batch_name only if classifier found one AND state doesn't already have one
    extracted_batch = parsed.get("batch_name")
    if extracted_batch:
        updates["batch_name"] = extracted_batch
    elif not state.get("batch_name"):
        updates["batch_name"] = None

    # Business date: prefer API-provided (already in state), then classifier, then today
    if not state.get("business_date"):
        updates["business_date"] = parsed.get("business_date") or today

    # Processing type: prefer API-provided, then classifier
    if not state.get("processing_type") and parsed.get("processing_type"):
        updates["processing_type"] = parsed["processing_type"]

    # prediction → set a placeholder response and short-circuit
    if intent == "prediction":
        updates["response_text"] = (
            "Runtime prediction is coming in a future release. "
            "For now, I can show you historical runtimes — just ask!"
        )
        updates["suggested_queries"] = [
            "How long did this batch take last week?",
            "What is the current status instead?",
        ]

    # general_query → placeholder until Tier 2 SQL analyst is implemented
    if intent == "general_query":
        updates["response_text"] = (
            "Ad-hoc analytical queries are coming in a future release. "
            "For now, I can check current batch status, investigate failures, "
            "or show task-level details for specific DAG runs."
        )
        updates["suggested_queries"] = [
            "What is the current status of this batch?",
            "What failed today?",
            "Show me historical runs for the last 5 days",
        ]

    return updates
