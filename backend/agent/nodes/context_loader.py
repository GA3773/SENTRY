"""Context loader node — restores state from previous turns via MemorySaver checkpoint."""

import logging

from agent.state import SentryState

log = logging.getLogger(__name__)

# Fields to carry forward from the previous turn's final state.
# These represent "conversation context" that should persist across turns
# unless the new turn explicitly overrides them.
CARRY_FORWARD_FIELDS = [
    "batch_name",
    "batch_definition",
    "dataset_ids",
    "business_date",
    "processing_type",
]


def context_loader(state: SentryState) -> dict:
    """Carry forward context fields from previous turn if not set in current input.

    LangGraph's MemorySaver preserves ALL state fields across invoke() calls
    for the same thread_id. However, when the API layer builds input_state for
    a new turn, it only sets 'messages', 'business_date', and 'processing_type'.

    This node ensures that batch context from the previous turn (batch_name,
    batch_definition, dataset_ids) survives into the new turn, enabling
    follow-up questions like "What about the EMEA slices?" without re-stating
    the batch name.

    If the new turn's intent_classifier extracts a NEW batch_name, it will
    overwrite the carried-forward value — which is the correct behavior.
    """
    # Nothing to do — MemorySaver already merged previous state.
    # This node exists as a documentation marker and future hook for
    # any pre-processing logic (e.g., clearing stale error state).

    updates: dict = {}

    # Clear error from previous turn so it doesn't short-circuit this turn
    if state.get("error"):
        updates["error"] = None
        log.debug("Cleared error from previous turn")

    # Clear previous turn's response fields
    updates["response_text"] = None
    updates["structured_data"] = None
    updates["suggested_queries"] = None
    updates["analysis"] = None
    updates["query_results"] = None
    updates["rca_findings"] = None

    return updates
