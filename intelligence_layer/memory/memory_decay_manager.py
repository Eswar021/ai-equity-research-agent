"""
intelligence_layer/memory/memory_decay_manager.py  —  Layer 4, Memory Decay Manager

Thin wrapper — delegates to canonical memory_qualification.memory_decay_manager.

Design doc: docs/system_design_docs/layer_4.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import DB_MEMORY_DIR
from intelligence_layer.memory_qualification import memory_decay_manager as _canonical


def run_decay(as_of_date: str | None = None,
              db_memory_dir: Path | None = None) -> dict:
    """
    Age out stale memory records based on TTL rules.
    Returns {expired_count, archived_count, stale_count, unchanged_count}.
    """
    return _canonical.run_decay(
        db_memory_dir=db_memory_dir or DB_MEMORY_DIR,
        as_of_date=as_of_date,
    )
