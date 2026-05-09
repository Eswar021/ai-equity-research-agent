"""
guardrails/final_output_guardrail.py  —  Cross-cutting Guardrails, Final Output Guardrail

Last-pass validator before the report is written. Checks:
- No unsupported buy/sell claims
- All source URLs are real (not hallucinated)
- Report doesn't exceed scope (no forward earnings predictions without basis)

Design doc: docs/system_design_docs/master_system_design.md (Cross-cutting Guardrails)
"""


def validate_final_output(report: dict) -> dict:
    """Returns {valid: bool, issues: list, report: dict (possibly redacted)}. Stub."""
    raise NotImplementedError
