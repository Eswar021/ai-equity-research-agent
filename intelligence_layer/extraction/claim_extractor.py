"""
intelligence_layer/extraction/claim_extractor.py  —  Layer 3, Claim Extractor

Extracts analyst opinions, management guidance, and qualitative claims.
Every claim is paired with its source URL for traceability (per AI_Content_Creation pattern).

Design doc: docs/system_design_docs/layer_3.md
"""


def extract_claims(doc: dict, llm) -> list[dict]:
    """Stub — implement per layer_3 design doc."""
    raise NotImplementedError
