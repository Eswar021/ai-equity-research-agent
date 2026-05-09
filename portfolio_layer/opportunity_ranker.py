"""
portfolio_layer/opportunity_ranker.py  —  Layer 10, Opportunity Ranker

Ranks all analyzed opportunities by conviction × expected return × regime fit.
Produces the final ordered list feeding the CIO synthesis and report.

Design doc: docs/system_design_docs/layer_6.md (Layer 10 section)
"""


def rank_opportunities(analyst_views: list[dict], regime: dict) -> list[dict]:
    """Returns ranked list of opportunities. Stub."""
    raise NotImplementedError
