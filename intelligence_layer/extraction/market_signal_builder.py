"""
intelligence_layer/extraction/market_signal_builder.py  —  Layer 3, Market Signal Builder

Assembles extracted entities, facts, events, claims, and themes into
a unified market signal record per entity. Used by target_ranker downstream.

Design doc: docs/system_design_docs/layer_3.md
"""


def build_signals(entities: list, facts: list, events: list, claims: list, themes: list) -> list[dict]:
    """Stub — implement per layer_3 design doc."""
    raise NotImplementedError
