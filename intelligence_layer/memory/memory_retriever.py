"""
intelligence_layer/memory/memory_retriever.py  —  Layer 4, Memory Retriever

Thin wrapper — delegates to canonical memory_qualification.memory_retriever.

Design doc: docs/system_design_docs/layer_4.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import DB_MEMORY_DIR
from intelligence_layer.memory_qualification import memory_retriever as _canonical


def retrieve(query_entities: list[str] | None = None,
             query_themes: list[str] | None = None,
             memory_type: str | None = None,
             limit: int = 20,
             db_memory_dir: Path | None = None) -> list[dict]:
    """
    Retrieve relevant memory records for a given set of entities / themes.
    Returns a flat list of memory summary dicts (confidence-sorted).
    """
    return _canonical.retrieve(
        query_entities=query_entities or [],
        query_themes=query_themes or [],
        db_memory_dir=db_memory_dir or DB_MEMORY_DIR,
        memory_types=[memory_type] if memory_type else None,
        limit=limit,
    )


def build_context_packet(current_entities: list[str],
                          current_themes: list[str],
                          run_id: str = "",
                          db_memory_dir: Path | None = None) -> dict:
    """Build the full memory context packet for Layer 5 / Layer 6."""
    return _canonical.build_context_packet(
        current_entities=current_entities,
        current_themes=current_themes,
        db_memory_dir=db_memory_dir or DB_MEMORY_DIR,
        run_id=run_id,
    )
