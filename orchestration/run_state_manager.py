"""
orchestration/run_state_manager.py  —  Layer 0, Run State Manager

Tracks pipeline run state: which phases completed, which failed, resume points.
Persists state to db/ so the pipeline can resume after a crash.

Design doc: docs/system_design_docs/layer_0_implementation_design.md
"""


def load_run_state(run_date: str) -> dict:
    """Stub — implement per layer_0 design doc."""
    raise NotImplementedError


def save_run_state(run_date: str, state: dict) -> None:
    """Stub — implement per layer_0 design doc."""
    raise NotImplementedError
