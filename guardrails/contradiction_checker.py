"""
guardrails/contradiction_checker.py  —  Cross-cutting Guardrails, Contradiction Checker

Detects contradictions between specialist agent views before thesis synthesis.
Example: valuation_agent says "expensive" but thesis_agent says "buy at current price".

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def check_contradictions(specialist_views: dict) -> dict:
    """Returns {contradictions: list, severity: str}. Stub."""
    raise NotImplementedError
