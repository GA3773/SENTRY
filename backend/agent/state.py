"""LangGraph state definition for the SENTRY agent."""

from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class SentryState(TypedDict):
    """Full state carried through every node in the SENTRY graph.

    `messages` uses the LangGraph add_messages reducer so each node can
    append new messages without overwriting the conversation history.
    All other fields are plain overwrite-on-write.
    """

    messages: Annotated[list, add_messages]

    # Intent classification
    intent: Optional[str]

    # Batch / essential resolution
    batch_name: Optional[str]
    batch_definition: Optional[dict]
    dataset_ids: Optional[List[str]]

    # Dataset-level targeting (when user asks about a specific dataset within a batch)
    dataset_ref: Optional[str]
    target_dataset: Optional[dict]

    # Slice-level targeting
    slice_ref: Optional[str]
    resolved_slices: Optional[List[str]]

    # Query context
    business_date: Optional[str]
    processing_type: Optional[str]

    # Results flowing through the pipeline
    query_results: Optional[dict]
    rca_findings: Optional[dict]

    # Analysis output (from analyzer node)
    analysis: Optional[dict]

    # Response assembly
    response_text: Optional[str]
    structured_data: Optional[dict]
    suggested_queries: Optional[List[str]]
    tool_calls_log: Optional[List[dict]]

    # Error state — any node can set this to short-circuit to response_synthesizer
    error: Optional[str]
