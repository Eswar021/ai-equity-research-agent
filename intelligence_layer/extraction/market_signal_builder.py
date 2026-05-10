"""
intelligence_layer/extraction/market_signal_builder.py  —  Layer 3, Market Signal Builder

Thin wrapper around canonical_intelligence_extraction structured extractor.

Design change from old stub: signals are built from structured records (FII/DII flows,
macro snapshots, derivatives data), NOT from assembled LLM-extracted objects.
The old interface build_signals(entities, facts, events, claims, themes) is superseded.

For full Layer 3 run use layer3_runner.run() instead.

Design doc: docs/system_design_docs/layer_3.md §14 market_signal_builder.py
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from intelligence_layer.canonical_intelligence_extraction.extractors.market_signal_builder import (
    build as _build,
)


def build_signals(record: dict) -> list[dict]:
    """
    Build market signal cards from a single canonical structured record.

    Supports: institutional_flow, macro_snapshot, derivatives_snapshot records.
    Returns [] for unsupported record types.

    Note: the previous interface build_signals(entities, facts, events, claims, themes)
    is superseded — market signals now come from rule-based structured record extraction,
    not from assembled LLM objects.
    """
    return _build(record)
