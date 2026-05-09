"""
intelligence_layer/research_target_planner/entity_resolver.py  —  Layer 6, Entity Resolver

Resolves entity names from Layer 3 extraction to canonical identifiers.
For listed entities: NSE ticker. For private: CIN or company name.
For sectors/macro: standardised taxonomy term.

Design doc: docs/system_design_docs/layer_6.md
"""


def resolve_entity(entity_name: str, entity_type: str) -> dict:
    """Returns {canonical_id, resolved_name, confidence}. Stub."""
    raise NotImplementedError
