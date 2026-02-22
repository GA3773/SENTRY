"""Batch resolver node — resolves natural language batch name to Lenz definition."""

import logging
import time

from agent.state import SentryState
from services.lenz_service import LenzService

log = logging.getLogger(__name__)

# Module-level singleton — cache survives across invocations within the process
_lenz_service = LenzService()


def batch_resolver(state: SentryState) -> dict:
    """Resolve batch_name → Lenz essential definition → dataset IDs.

    Populates batch_definition and dataset_ids in state.
    Sets error if batch cannot be resolved.
    """
    batch_name = state.get("batch_name")
    if not batch_name:
        return {"error": "No batch name found in the conversation. Which essential would you like to check?"}

    tool_calls_log = list(state.get("tool_calls_log") or [])

    t0 = time.time()
    try:
        definition = _lenz_service.get_essential_definition(batch_name)
    except ValueError as e:
        log.warning("Batch resolution failed for '%s': %s", batch_name, e)
        return {"error": str(e)}
    except Exception as e:
        log.error("Lenz API error resolving '%s': %s", batch_name, e)
        return {"error": f"Failed to resolve batch '{batch_name}': {e}"}

    duration_ms = int((time.time() - t0) * 1000)
    tool_calls_log.append({
        "tool": "resolve_batch",
        "input": {"batch_name": batch_name},
        "duration_ms": duration_ms,
    })

    definition_dict = definition.model_dump()
    dataset_ids = definition.dataset_ids

    log.info(
        "Resolved '%s' → %s (%d datasets)",
        batch_name,
        definition.essential_name,
        len(dataset_ids),
    )

    return {
        "batch_name": definition.display_name,
        "batch_definition": definition_dict,
        "dataset_ids": dataset_ids,
        "tool_calls_log": tool_calls_log,
    }
