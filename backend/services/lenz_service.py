"""
Lenz API service for SENTRY.

Provides batch (Essential) definitions: which datasets belong to a batch,
their execution sequence, and valid slices per dataset.

The Lenz API is behind ADFS (form-based OAuth2 login).
Authentication is handled by lenz_auth.py (session-based, cookie reuse).
Calls are cached with 5-min TTL so sync requests have negligible impact.
"""

import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv

from config.essentials_map import ESSENTIAL_MAP
from models.lenz import DatasetDef, EssentialDef
from services.lenz_auth import lenz_fetch

load_dotenv()

log = logging.getLogger(__name__)


def _parse_lenz_response(raw: dict, essential_name: str) -> EssentialDef:
    """Parse the nested Lenz API response into an EssentialDef.

    Handles all three sliceGroups formats:
      1. Flat:   {"slices": ["PB-GLOBAL-SLICE", ...]}
      2. Named:  {"DERIV": ["AWS_OTC_DERIV_AGG_EMEA", ...]}
      3. Absent: no sliceGroups key at all
    """
    essential_data = raw.get("GLOBAL", {}).get(essential_name, {})

    if not essential_data:
        raise ValueError(f"Essential '{essential_name}' not found in Lenz response")

    datasets_raw = essential_data.get("schemaJson", {}).get("datasets", [])

    datasets: list[DatasetDef] = []
    for d in datasets_raw:
        slice_groups: Optional[dict[str, list[str]]] = None
        if "sliceGroups" in d and d["sliceGroups"]:
            slice_groups = {}
            for key, value in d["sliceGroups"].items():
                if isinstance(value, list):
                    slice_groups[key] = value

        datasets.append(
            DatasetDef(
                dataset_id=d["datasetId"],
                sequence_order=d.get("sequenceOrder", 0),
                slice_groups=slice_groups if slice_groups else None,
            )
        )

    datasets.sort(key=lambda x: x.sequence_order)

    return EssentialDef(
        essential_name=essential_data.get("essentialName", essential_name),
        display_name=essential_data.get("displayName", essential_name),
        context=essential_data.get("context", "GLOBAL"),
        datasets=datasets,
    )


def resolve_essential_name(user_input: str) -> Optional[str]:
    """Resolve a user-facing batch name to a Lenz essential name.

    Case-insensitive lookup against ESSENTIAL_MAP.
    Returns None if no match is found.
    """
    normalized = user_input.strip().upper()

    # Exact match (case-insensitive)
    if normalized in ESSENTIAL_MAP:
        return ESSENTIAL_MAP[normalized]

    # Fuzzy: check if input is a substring of any key or value
    for key, value in ESSENTIAL_MAP.items():
        if normalized in key or normalized in value.upper():
            return value

    return None


def resolve_slice_filter(
    essential_def: EssentialDef, dataset_id: str, user_ref: str
) -> list[str]:
    """Map a fuzzy user slice reference to actual slice names from Lenz.

    Example: user_ref="EMEA" for intercompany dataset → all EMEA slices.
    """
    dataset = next(
        (d for d in essential_def.datasets if d.dataset_id == dataset_id), None
    )
    if not dataset:
        return []
    all_slices = dataset.all_slices
    normalized = user_ref.upper().replace(" ", "_").replace("-", "_")
    return [s for s in all_slices if normalized in s.upper().replace("-", "_")]


class LenzService:
    """Lenz API client with in-memory caching."""

    def __init__(self) -> None:
        self._ttl = int(os.getenv("LENZ_CACHE_TTL", "300"))
        self._cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_get(self, essential_name: str) -> Optional[EssentialDef]:
        entry = self._cache.get(essential_name)
        if entry and (time.time() - entry["timestamp"]) < self._ttl:
            return entry["data"]
        return None

    def _cache_set(self, essential_name: str, data: EssentialDef) -> None:
        self._cache[essential_name] = {"data": data, "timestamp": time.time()}

    def invalidate(self, essential_name: Optional[str] = None) -> None:
        """Clear cache for one essential or all."""
        if essential_name:
            self._cache.pop(essential_name, None)
        else:
            self._cache.clear()

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def get_essential_definition(self, name: str) -> EssentialDef:
        """Resolve user input to an essential name and fetch its definition.

        Args:
            name: User-facing name (e.g. "DERIV", "6G", "SNU").

        Returns:
            Parsed EssentialDef with datasets and slices.
        """
        essential_name = resolve_essential_name(name)
        if not essential_name:
            raise ValueError(
                f"Unknown essential: '{name}'. "
                f"Valid names: {', '.join(sorted(ESSENTIAL_MAP.keys()))}"
            )

        # Check cache
        cached = self._cache_get(essential_name)
        if cached:
            log.debug("Cache hit for %s", essential_name)
            return cached

        # Fetch from API via authenticated session
        log.info("Fetching Lenz definition for %s", essential_name)
        raw = lenz_fetch(essential_name)
        definition = _parse_lenz_response(raw, essential_name)

        self._cache_set(essential_name, definition)
        return definition

    def get_dataset_ids(self, name: str) -> list[str]:
        """Get all dataset IDs for an essential."""
        definition = self.get_essential_definition(name)
        return definition.dataset_ids

    def get_datasets_by_sequence(
        self, name: str
    ) -> dict[int, list[DatasetDef]]:
        """Get datasets grouped by sequence order."""
        definition = self.get_essential_definition(name)
        return definition.datasets_by_sequence()

    def get_valid_slices(self, name: str, dataset_id: str) -> list[str]:
        """Get all valid slice names for a specific dataset within an essential."""
        definition = self.get_essential_definition(name)
        dataset = next(
            (d for d in definition.datasets if d.dataset_id == dataset_id), None
        )
        if not dataset:
            return []
        return dataset.all_slices

    def prefetch_all(self) -> None:
        """Pre-fetch definitions for all known essentials."""
        unique_names = set(ESSENTIAL_MAP.values())
        for essential_name in sorted(unique_names):
            try:
                raw = lenz_fetch(essential_name)
                definition = _parse_lenz_response(raw, essential_name)
                self._cache_set(essential_name, definition)
                log.info(
                    "Pre-fetched: %s (%d datasets)",
                    essential_name,
                    len(definition.datasets),
                )
            except Exception as e:
                log.warning("Failed to pre-fetch %s: %s", essential_name, e)
