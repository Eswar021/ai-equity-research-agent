"""
guardrails/source_traceability_checker.py  —  Cross-cutting Guardrails, Source Traceability Checker

Checks that source URLs in analyst output actually exist in the signal chain
(Layer 1 raw → Layer 3 extraction → Layer 8 evidence card → Layer 9 output).

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def check_traceability(analyst_view: dict, signal_chain: dict) -> dict:
    """Returns {traceable: bool, broken_links: list}. Stub."""
    raise NotImplementedError
