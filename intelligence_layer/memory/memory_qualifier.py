"""
intelligence_layer/memory/memory_qualifier.py  —  Layer 4, Memory Qualification Agent

Thin wrapper — delegates to canonical memory_qualification module.

Design doc: docs/system_design_docs/layer_4.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from intelligence_layer.memory_qualification import (
    memory_candidate_builder,
    memory_relevance_scorer,
    novelty_checker,
    recurrence_tracker,
    memory_type_classifier,
    memory_qualification_agent,
)


def qualify_for_memory(candidate: dict, entity_index: dict | None = None,
                       theme_index: dict | None = None,
                       existing_records: list | None = None) -> dict:
    """
    Run the full qualification pipeline for a single memory candidate.

    Returns memory_decision dict:
        {decision, memory_type, memory_score, retention_days, ...}
    """
    ei = entity_index or {}
    ti = theme_index  or {}
    er = existing_records or []

    novelty_r    = novelty_checker.check(candidate, ei, ti)
    recurrence_r = recurrence_tracker.track(candidate, er)
    score_r      = memory_relevance_scorer.score(
        candidate,
        recurrence=recurrence_r,
        novelty_status=novelty_r["novelty_status"],
    )
    classification = memory_type_classifier.classify(
        candidate,
        score_r["memory_score"],
        novelty_r["novelty_status"],
        recurrence_r,
    )
    return memory_qualification_agent.decide(
        candidate, score_r["memory_score"],
        novelty_r, recurrence_r, classification,
    )
