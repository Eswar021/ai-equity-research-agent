"""
intelligence_layer/extraction/entity_extractor.py  —  Layer 3, Entity Extractor

LLM call per document: extracts named entities (listed companies, private companies,
sectors, macro indicators, policy bodies) with entity_type classification.

Design doc: docs/system_design_docs/layer_3.md
"""


def extract_entities(doc: dict, llm) -> list[dict]:
    """Stub — implement per layer_3 design doc."""
    raise NotImplementedError
