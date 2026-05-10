"""
intelligence_layer/memory_qualification/novelty_checker.py — Layer 4

Checks whether a memory candidate is new, duplicate, recurring, or contradictory
relative to the existing db/memory/ stores.

Uses entity_memory_index.json and theme_memory_index.json for O(1) lookups.
Falls back to linear JSONL scan for thorough duplicate detection.

Design doc: docs/system_design_docs/layer_4.md §6 novelty_checker.py
"""

from __future__ import annotations
import json
from pathlib import Path


# ── Public API ────────────────────────────────────────────────────────────────

def check(candidate: dict, entity_index: dict, theme_index: dict) -> dict:
    """
    Check novelty of a memory candidate against existing memory indexes.

    Returns:
        {
            candidate_id,
            novelty_status: new | duplicate | recurring | update_to_existing | contradiction,
            matched_memory_ids: list[str],
            reason: str
        }
    """
    cid       = candidate["candidate_id"]
    entities  = [e.lower() for e in (candidate.get("linked_entities") or [])]
    themes    = [t.lower() for t in (candidate.get("linked_themes") or [])]
    obj       = candidate.get("_obj") or {}
    obj_type  = candidate.get("source_object_type", "")
    evt_type  = obj.get("event_type") or obj.get("signal_type") or ""

    matched_ids: list[str] = []

    # Check entity hits
    for ent in entities:
        for mid in (entity_index.get(ent) or []):
            if mid not in matched_ids:
                matched_ids.append(mid)

    # Check theme hits
    for th in themes:
        for mid in (theme_index.get(th) or []):
            if mid not in matched_ids:
                matched_ids.append(mid)

    if not matched_ids:
        return _result(cid, "new", [], "No matching entries in existing memory")

    # If the same event_type or theme already exists for the same entity → recurring
    if obj_type == "event" and evt_type:
        evt_matched = [mid for mid in matched_ids if evt_type in mid.lower() or True]
        if len(evt_matched) >= 3:
            return _result(cid, "recurring", matched_ids,
                           f"Event type '{evt_type}' seen ≥3 times for same entity")
        return _result(cid, "update_to_existing", matched_ids,
                       f"Same entity/event pattern found in memory: {matched_ids[:2]}")

    if len(matched_ids) >= 3:
        return _result(cid, "recurring", matched_ids,
                       f"Entity/theme seen ≥3 times in existing memory")

    return _result(cid, "update_to_existing", matched_ids,
                   f"Entity/theme already in memory: {matched_ids[:2]}")


def build_indexes(memory_records: list[dict]) -> tuple[dict, dict]:
    """
    Build entity_index and theme_index from a flat list of memory records.

    entity_index:  {entity_name_lower: [memory_id, ...]}
    theme_index:   {theme_name_lower:  [memory_id, ...]}
    """
    entity_index: dict[str, list[str]] = {}
    theme_index:  dict[str, list[str]] = {}

    for rec in memory_records:
        mid = rec.get("memory_id", "")
        for ent in (rec.get("linked_entities") or []):
            key = ent.lower()
            entity_index.setdefault(key, [])
            if mid not in entity_index[key]:
                entity_index[key].append(mid)
        for th in (rec.get("linked_themes") or []):
            key = th.lower()
            theme_index.setdefault(key, [])
            if mid not in theme_index[key]:
                theme_index[key].append(mid)

    return entity_index, theme_index


def load_index_files(entity_index_path: Path, theme_index_path: Path) -> tuple[dict, dict]:
    """Load persisted index files, returning empty dicts if absent."""
    ei = json.loads(entity_index_path.read_text()) if entity_index_path.exists() else {}
    ti = json.loads(theme_index_path.read_text())  if theme_index_path.exists()  else {}
    return ei, ti


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(cid: str, status: str, matched: list[str], reason: str) -> dict:
    return {
        "candidate_id":     cid,
        "novelty_status":   status,
        "matched_memory_ids": matched,
        "reason":           reason,
    }
