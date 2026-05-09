"""
orchestration/schemas.py  —  Layer 0, Shared Orchestration Schemas

Pydantic models shared across orchestration modules: RunMode, CollectionPlan,
RunState, BudgetConfig.

Design doc: docs/system_design_docs/layer_0_implementation_design.md
"""
from pydantic import BaseModel


class RunMode(BaseModel):
    """Stub — implement per layer_0 design doc."""
    pass


class CollectionPlan(BaseModel):
    """Stub — implement per layer_0 design doc."""
    pass
