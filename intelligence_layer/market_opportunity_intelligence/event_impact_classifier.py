"""
intelligence_layer/market_opportunity_intelligence/event_impact_classifier.py  —  Layer 5, Event Impact Classifier

Classifies market events by their potential impact: magnitude, time horizon,
affected sectors. Distinguishes one-time events from structural changes.

Design doc: docs/system_design_docs/layer_5.md
"""


def classify_impact(event: dict, llm) -> dict:
    """Returns {magnitude, time_horizon, affected_sectors, is_structural}. Stub."""
    raise NotImplementedError
