"""
agents/thesis_agent.py  —  Layer 9, Thesis Agent

Synthesizes all specialist agent views into a final structured recommendation:
invest/watch/avoid, conviction, thesis narrative, key drivers, key risks,
time horizon, price action, and cited source URLs.

This is the v2 evolution of stock_analyst.py (multi-agent ensemble vs single agent).

Design doc: docs/system_design_docs/layer_6.md (Layer 9 section)
"""


def synthesize_thesis(specialist_views: dict, context_packet: dict, llm) -> dict:
    """Returns final thesis dict. Stub — v2 evolution of stock_analyst.py."""
    raise NotImplementedError
