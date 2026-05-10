"""
intelligence_layer/memory/thesis_memory_manager.py  —  Layer 4, Thesis Memory Manager

Thin wrapper — delegates to canonical memory_qualification.thesis_memory_manager.

Design doc: docs/system_design_docs/layer_4.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import DB_THESIS_MEMORY_FILE
from intelligence_layer.memory_qualification import thesis_memory_manager as _canonical


def upsert_thesis(candidate: dict, decision: dict,
                  entity_index: dict | None = None,
                  thesis_file: Path | None = None) -> dict | None:
    """
    Create a new thesis or update an existing one for this candidate.
    Returns the thesis record, or None if not applicable.
    """
    return _canonical.process(
        candidate=candidate,
        decision=decision,
        thesis_file=thesis_file or DB_THESIS_MEMORY_FILE,
        entity_index=entity_index or {},
    )
