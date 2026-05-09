"""
intelligence_layer/memory/memory_qualifier.py  —  Layer 4, Memory Qualification Agent

LLM agent that evaluates each extracted signal and decides whether it is
significant enough to be stored in memory. Filters noise from structural signals.

Design doc: docs/system_design_docs/layer_4.md
"""


def qualify_for_memory(signal: dict, llm) -> dict:
    """Returns {should_store: bool, memory_type: str, ttl_days: int}. Stub."""
    raise NotImplementedError
