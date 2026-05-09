"""
intelligence_layer/memory/memory_writer.py  —  Layer 4, Memory Writer

Writes qualified signals to the appropriate memory tier:
working_memory, short_term_market_memory, watch_memory, long_term_investment_memory.
Also processes memory_update_instructions.json from Layer 10 feedback.

Design doc: docs/system_design_docs/layer_4.md
"""


def write_to_memory(qualified_signal: dict, memory_type: str) -> str:
    """Returns memory_record_id. Stub — implement per layer_4 design doc."""
    raise NotImplementedError


def apply_memory_updates(instructions_path: str) -> dict:
    """Processes Layer 10 → Layer 4 feedback instructions. Stub."""
    raise NotImplementedError
