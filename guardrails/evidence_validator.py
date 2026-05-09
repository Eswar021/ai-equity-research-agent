"""
guardrails/evidence_validator.py  —  Cross-cutting Guardrails, Evidence Validator

Validates that every claim in analyst output has a traceable source URL
in the evidence card. Rejects recommendations without cited evidence.

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def validate_evidence(analyst_view: dict, evidence_card: dict) -> dict:
    """Returns {valid: bool, violations: list}. Stub."""
    raise NotImplementedError
