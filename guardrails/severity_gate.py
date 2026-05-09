"""
guardrails/severity_gate.py  —  Cross-cutting Guardrails, Severity Gate

Hard gate: blocks "invest" recommendation if any high-severity red flag
is present (D/E > 2, regulatory action, consecutive quarters of loss).

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def apply_severity_gate(analyst_view: dict, evidence_card: dict) -> dict:
    """Returns analyst_view, possibly forced to 'avoid' or 'watch'. Stub."""
    raise NotImplementedError
