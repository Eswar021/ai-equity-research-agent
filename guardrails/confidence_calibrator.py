"""
guardrails/confidence_calibrator.py  —  Cross-cutting Guardrails, Confidence Calibrator

Lowers conviction by one notch when evidence_card.data_gaps is non-empty
or when source count < minimum threshold for the recommendation level.

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def calibrate_confidence(analyst_view: dict, evidence_card: dict) -> dict:
    """Returns analyst_view with potentially adjusted conviction. Stub."""
    raise NotImplementedError
