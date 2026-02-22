"""Pydantic models for Lenz API responses."""

from collections import defaultdict
from typing import Optional

from pydantic import BaseModel


class DatasetDef(BaseModel):
    dataset_id: str
    sequence_order: int
    slice_groups: Optional[dict[str, list[str]]] = None

    @property
    def all_slices(self) -> list[str]:
        """Flattens all slice groups into a single list."""
        if not self.slice_groups:
            return []
        slices: list[str] = []
        for group_slices in self.slice_groups.values():
            slices.extend(group_slices)
        return slices


class EssentialDef(BaseModel):
    essential_name: str
    display_name: str
    context: str
    datasets: list[DatasetDef]

    @property
    def dataset_ids(self) -> list[str]:
        return [d.dataset_id for d in self.datasets]

    def datasets_by_sequence(self) -> dict[int, list[DatasetDef]]:
        """Groups datasets by sequence order. Same order = parallel execution."""
        grouped: dict[int, list[DatasetDef]] = defaultdict(list)
        for d in self.datasets:
            grouped[d.sequence_order].append(d)
        return dict(sorted(grouped.items()))
