"""
orchestration/run_mode_detector.py  —  Layer 0, Run Mode Detector

Determines how the pipeline should run: full daily run, incremental refresh,
single-ticker debug, or backfill mode.

Design doc: docs/system_design_docs/layer_0_implementation_design.md
"""


def detect_run_mode() -> dict:
    """Returns run mode config dict. Stub — implement per layer_0 design doc."""
    raise NotImplementedError
