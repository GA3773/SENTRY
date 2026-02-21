# Lenz API Integration

## Overview
The Lenz API is the SINGLE SOURCE OF TRUTH for batch (Essential) definitions. It provides:
- Which datasets belong to a batch
- Execution sequence order (sequenceOrder)
- Valid slices per dataset (sliceGroups)

SENTRY MUST resolve every batch reference through Lenz before querying databases.

## API Endpoint
```
GET https://lenz-app.prod.aws.jpmchase.net/lenz/essentials/def?name={essential_name}
```

## Essential Name Mapping
Users refer to batches by common names. Map to Lenz essential names:

```python
ESSENTIAL_MAP = {
    # User-facing name (uppercase) → Lenz essential name
    "6G": "6G-FR2052a-E2E",
    "FR2052A": "6G-FR2052a-E2E",
    "PBSYNTHETICS": "PBSynthetics",
    "SNU": "SNU",
    "SNU STRATEGIC": "SNU-Strategic",
    "SNU REG STRATEGIC": "SNU-REG-STRATEGIC",
    "COLLATERAL": "TB-Collateral",
    "DERIVATIVES": "TB-Derivatives",
    "DERIV": "TB-Derivatives",
    "SECURITIES": "TB-Securities",
    "SECFIN": "TB-SecFIn",
    "CFG": "TB-CFG",
    "SMAA": "TB-SMAA",
    "UPC": "UPC",
}
```

This is the ONLY static config. Everything else comes from the API.

## Response Structure

Example for TB-Derivatives:
```json
{
  "GLOBAL": {
    "TB-Derivatives": {
      "essentialName": "TB-Derivatives",
      "context": "GLOBAL",
      "effectiveFrom": "2025-10-24T17:33:32",
      "effectiveTo": null,
      "displayName": "TB-Derivatives",
      "modifiedByUserSid": "R735452",
      "info": null,
      "schemaJson": {
        "datasets": [
          {
            "datasetId": "com.jpmc.ct.lri.derivatives-pb_synthetics_trs_e15",
            "sliceGroups": {
              "slices": [
                "PB-GLOBAL-SLICE",
                "PB-REGIONAL-SLICE",
                "PB-EMEA-SLICE",
                "PB-NA-SLICE",
                "PB-APAC-SLICE"
              ]
            },
            "sequenceOrder": 0
          },
          {
            "datasetId": "com.jpmc.ct.lri.derivatives-slsline_calculator_e15",
            "sequenceOrder": 0
          },
          {
            "datasetId": "com.jpmc.ct.lri.derivatives-calc_intercompany_fx_adjustment_e15",
            "sequenceOrder": 1
          },
          {
            "datasetId": "com.jpmc.ct.lri.derivatives-calc_secured_vs_unsecured_e15",
            "sequenceOrder": 2
          },
          {
            "datasetId": "com.jpmc.ct.lri.cfg-contractual_cash_flow_results_v1",
            "sliceGroups": {
              "DERIV": [
                "EMEA_DERIV_CFG",
                "EMEA_SEC_VS_UNSEC_CFG",
                "GLOBAL_DERIV_CFG",
                "GLOBAL_SEC_VS_UNSEC_CFG",
                "GLOBAL_PBSYNTHETICS_CFG"
              ]
            },
            "sequenceOrder": 3
          },
          {
            "datasetId": "com.jpmc.ct.lri.sls-sls_aws_details_extended_v1",
            "sliceGroups": {
              "DERIV": [
                "AWS_CRI_OTC_DERIV_EMEA",
                "AWS_OTC_DERIV_AGG_EMEA",
                "AWS_CRI_OTC_DERIV_GLOBAL",
                "AWS_OTC_DERIV_AGG_GLOBAL",
                "GLOBAL_SEC_VS_UNSEC_CFG",
                "EMEA_SEC_VS_UNSEC_CFG",
                "AWS_DERIV_PB_SYNTHETIC_GLOBAL"
              ]
            },
            "sequenceOrder": 4
          },
          {
            "datasetId": "com.jpmc.ct.lri.intercompany-intercompany_results",
            "sliceGroups": {
              "DERIV": [
                "AWS_OTC_DERIV_AGG_EMEA",
                "AWS_CRI_OTC_DERIV_EMEA",
                "AWS_DERIV_PB_SYNTHETIC_EMEA",
                "AWS_OTC_DERIV_AGG_GLOBAL",
                "AWS_CRI_OTC_DERIV_GLOBAL"
              ]
            },
            "sequenceOrder": 5
          }
        ]
      }
    }
  }
}
```

## Parsing Logic

### CRITICAL: Two slice group formats exist

**Format 1: Flat slices array**
```json
"sliceGroups": {
  "slices": ["PB-GLOBAL-SLICE", "PB-NA-SLICE", "PB-EMEA-SLICE"]
}
```

**Format 2: Named group with array**
```json
"sliceGroups": {
  "DERIV": ["AWS_OTC_DERIV_AGG_EMEA", "AWS_CRI_OTC_DERIV_EMEA"]
}
```

**Format 3: No sliceGroups at all**
```json
{
  "datasetId": "com.jpmc.ct.lri.derivatives-slsline_calculator_e15",
  "sequenceOrder": 0
}
```

The parsing code must handle all three. When sliceGroups is absent, the dataset has no slice-level parallelism (or its slices are defined in DAG_RUN_ID patterns but not in Lenz).

### Pydantic Models
```python
from pydantic import BaseModel
from typing import Optional, Dict, List, Union

class DatasetDef(BaseModel):
    dataset_id: str
    sequence_order: int
    slice_groups: Optional[Dict[str, List[str]]] = None  # key = group name or "slices"
    
    @property
    def all_slices(self) -> List[str]:
        """Flattens all slice groups into a single list."""
        if not self.slice_groups:
            return []
        slices = []
        for group_slices in self.slice_groups.values():
            slices.extend(group_slices)
        return slices

class EssentialDef(BaseModel):
    essential_name: str
    display_name: str
    context: str
    datasets: List[DatasetDef]

    @property
    def dataset_ids(self) -> List[str]:
        return [d.dataset_id for d in self.datasets]

    def datasets_by_sequence(self) -> Dict[int, List[DatasetDef]]:
        """Groups datasets by sequence order. Same order = parallel execution."""
        from collections import defaultdict
        grouped = defaultdict(list)
        for d in self.datasets:
            grouped[d.sequence_order].append(d)
        return dict(sorted(grouped.items()))
```

### Response Parsing
```python
def parse_lenz_response(raw: dict, essential_name: str) -> EssentialDef:
    """Parses the nested Lenz API response into an EssentialDef."""
    # Navigate the nested structure
    essential_data = raw.get("GLOBAL", {}).get(essential_name, {})
    
    if not essential_data:
        raise ValueError(f"Essential '{essential_name}' not found in Lenz response")
    
    datasets_raw = essential_data.get("schemaJson", {}).get("datasets", [])
    
    datasets = []
    for d in datasets_raw:
        slice_groups = None
        if "sliceGroups" in d and d["sliceGroups"]:
            slice_groups = {}
            for key, value in d["sliceGroups"].items():
                if isinstance(value, list):
                    slice_groups[key] = value
        
        datasets.append(DatasetDef(
            dataset_id=d["datasetId"],
            sequence_order=d.get("sequenceOrder", 0),
            slice_groups=slice_groups
        ))
    
    # Sort by sequence order
    datasets.sort(key=lambda x: x.sequence_order)
    
    return EssentialDef(
        essential_name=essential_data.get("essentialName", essential_name),
        display_name=essential_data.get("displayName", essential_name),
        context=essential_data.get("context", "GLOBAL"),
        datasets=datasets
    )
```

## Caching Strategy

- Cache TTL: 300 seconds (5 minutes)
- Pre-fetch all essentials on startup
- Cache invalidation: manual via API endpoint or user command
- Cache key: essential_name
- On cache miss: fetch from Lenz API, parse, store in cache

```python
import time
from typing import Dict, Optional

class LenzCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: Dict[str, dict] = {}  # {essential_name: {"data": EssentialDef, "timestamp": float}}
    
    def get(self, essential_name: str) -> Optional[EssentialDef]:
        entry = self._cache.get(essential_name)
        if entry and (time.time() - entry["timestamp"]) < self.ttl:
            return entry["data"]
        return None
    
    def set(self, essential_name: str, data: EssentialDef):
        self._cache[essential_name] = {"data": data, "timestamp": time.time()}
    
    def invalidate(self, essential_name: Optional[str] = None):
        if essential_name:
            self._cache.pop(essential_name, None)
        else:
            self._cache.clear()
```

## Slice Resolution for User Queries

When a user says "EMEA slices for derivatives intercompany":
1. Resolve "derivatives" → "TB-Derivatives" → Lenz API
2. Find dataset matching "intercompany" → `com.jpmc.ct.lri.intercompany-intercompany_results`
3. Get slices for that dataset → `["AWS_OTC_DERIV_AGG_EMEA", "AWS_CRI_OTC_DERIV_EMEA", "AWS_DERIV_PB_SYNTHETIC_EMEA", ...]`
4. Filter slices containing "EMEA" → 3 matching slices
5. Use these to filter DAG_RUN_ID in WORKFLOW_RUN_INSTANCE queries

```python
def resolve_slice_filter(essential_def: EssentialDef, dataset_id: str, user_ref: str) -> List[str]:
    """Maps fuzzy user slice reference to actual slice names from Lenz."""
    dataset = next((d for d in essential_def.datasets if d.dataset_id == dataset_id), None)
    if not dataset:
        return []
    all_slices = dataset.all_slices
    normalized = user_ref.upper().replace(" ", "_").replace("-", "_")
    return [s for s in all_slices if normalized in s.upper().replace("-", "_")]
```
