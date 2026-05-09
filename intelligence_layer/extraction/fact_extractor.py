"""
intelligence_layer/extraction/fact_extractor.py  —  Layer 3, Fact Extractor

Extracts verifiable numeric facts from documents: revenue, EPS, guidance numbers,
macro figures. Each fact carries source_url, date, and confidence.

Design doc: docs/system_design_docs/layer_3.md
"""


def extract_facts(doc: dict, llm) -> list[dict]:
    """Stub — implement per layer_3 design doc."""
    raise NotImplementedError
