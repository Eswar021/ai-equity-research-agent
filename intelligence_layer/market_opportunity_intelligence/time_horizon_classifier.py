"""
intelligence_layer/market_opportunity_intelligence/time_horizon_classifier.py  —  Layer 5, Time Horizon Classifier

Classifies each opportunity/hypothesis by investment time horizon:
short (< 3 months), medium (3-12 months), long (> 12 months).

Design doc: docs/system_design_docs/layer_5.md
"""


def classify_horizon(opportunity: dict) -> str:
    """Returns 'short' | 'medium' | 'long'. Stub."""
    raise NotImplementedError
