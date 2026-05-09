"""
evidence_layer/context_packet_builder.py  —  Layer 8, Context Packet Builder

Assembles the full context packet sent to each specialist agent:
evidence card + thesis card + relevant memory excerpts + regime context.

Design doc: docs/system_design_docs/layer_5.md (Evidence Builder section)
"""


def build_context_packet(ticker: str, as_of_date: str) -> dict:
    """Returns full context packet dict for agents. Stub."""
    raise NotImplementedError
