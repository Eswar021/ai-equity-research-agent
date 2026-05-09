"""
intelligence_layer/source_canonicalization/source_registry.py  —  Layer 2, Source Registry

Maintains a registry of all ingested sources: URL, source_type, reliability_tier,
first_seen, last_seen. Enables deduplication and source quality tracking.

Design doc: docs/system_design_docs/layer_2.md
"""


def register_source(url: str, source_type: str, metadata: dict) -> str:
    """Returns source_id. Stub — implement per layer_2 design doc."""
    raise NotImplementedError
