"""
agents/risk_agent.py  —  Layer 9, Risk Agent

Specialist agent enumerating key risks: regulatory, competitive, execution,
macro, balance sheet. Each risk gets severity + probability rating.

Design doc: docs/system_design_docs/layer_6.md (Layer 9 section)
"""


def analyze_risks(context_packet: dict, llm) -> dict:
    """Returns risk_view dict. Stub."""
    raise NotImplementedError
