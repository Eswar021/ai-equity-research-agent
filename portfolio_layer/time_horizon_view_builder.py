"""
portfolio_layer/time_horizon_view_builder.py  —  Layer 10, Time Horizon View Builder

Groups opportunities by time horizon (short/medium/long) and builds
horizon-specific portfolio views for the final report.

Design doc: docs/system_design_docs/layer_6.md (Layer 10 section)
"""


def build_horizon_views(ranked_opportunities: list[dict]) -> dict:
    """Returns {short: [...], medium: [...], long: [...]}. Stub."""
    raise NotImplementedError
