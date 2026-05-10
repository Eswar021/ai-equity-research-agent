"""
intelligence_layer/memory/memory_writer.py  —  Layer 4, Memory Writer

Thin wrapper — delegates to canonical memory_qualification.memory_writer.

Design doc: docs/system_design_docs/layer_4.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import DB_MEMORY_DIR
from intelligence_layer.memory_qualification import memory_writer as _canonical


def write_to_memory(candidate: dict, decision: dict,
                    db_memory_dir: Path | None = None) -> dict | None:
    """
    Write a new memory record for the given candidate + decision.
    Returns the written record, or None if the decision type does not produce a new record.
    """
    return _canonical.write(candidate, decision, db_memory_dir or DB_MEMORY_DIR)


def apply_memory_updates(instructions_path: str) -> dict:
    """Processes Layer 10 → Layer 4 feedback instructions. Not yet implemented."""
    raise NotImplementedError("Layer 10 feedback processing is a v2 feature")
