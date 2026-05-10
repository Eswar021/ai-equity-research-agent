"""
intelligence_layer/market_opportunity_intelligence/intelligence_memory_loader.py — Layer 5

Loads Layer 3 intelligence outputs + Layer 4 memory context packet into a single
unified dict consumed by every Layer 5 module.

Also pre-builds lookup maps (entity name → memory_ids, theme → memory_ids)
so signal_aggregator and other modules don't have to re-read memory files.

Design doc: docs/system_design_docs/layer_5.md §2 intelligence_memory_loader.py
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer3_dir: Path, layer4_dir: Path) -> dict:
    """
    Load current-run intelligence and Layer 4 memory context.

    Returns:
        {
            entities, facts, claims, events, themes, market_signals,
            object_links,
            memory_context,          # full memory_context_packet dict
            active_theses,           # list from thesis memory
            entity_memory_map,       # {entity_name_lower: [memory_id,...]}
            theme_memory_map,        # {theme_name_lower: [memory_id,...]}
            load_summary
        }
    """
    l3 = Path(layer3_dir)
    l4 = Path(layer4_dir)

    def _read(fname: str) -> list | dict:
        p = l3 / fname
        return json.loads(p.read_text()) if p.exists() else []

    entities       = _read("entity_registry.json")
    facts          = _read("fact_cards.json")
    claims         = _read("claim_cards.json")
    events         = _read("event_cards.json")
    themes         = _read("theme_cards.json")
    market_signals = _read("market_signal_cards.json")
    object_links   = _read("object_link_map.json")

    # entity_registry may be wrapped dict
    if isinstance(entities, dict) and "entities" in entities:
        entities = entities["entities"]
    if isinstance(object_links, dict) and "links" in object_links:
        object_links = object_links["links"]

    # Load memory context packet from L4
    mcp_path = l4 / "memory_context_packet.json"
    memory_context = json.loads(mcp_path.read_text()) if mcp_path.exists() else {}
    active_theses  = memory_context.get("relevant_thesis_memory") or []

    # Build quick-lookup maps from memory context
    entity_memory_map: dict[str, list[str]] = {}
    theme_memory_map:  dict[str, list[str]] = {}

    all_memory_records = (
        (memory_context.get("relevant_short_term_memory") or []) +
        (memory_context.get("relevant_watch_memory") or []) +
        (memory_context.get("relevant_long_term_memory") or []) +
        active_theses
    )
    for rec in all_memory_records:
        mid = rec.get("memory_id") or rec.get("thesis_id") or ""
        for ent in (rec.get("linked_entities") or []):
            key = ent.lower()
            entity_memory_map.setdefault(key, [])
            if mid not in entity_memory_map[key]:
                entity_memory_map[key].append(mid)
        for th in (rec.get("linked_themes") or []):
            key = th.lower()
            theme_memory_map.setdefault(key, [])
            if mid not in theme_memory_map[key]:
                theme_memory_map[key].append(mid)

    load_summary = {
        "entities":       len(entities),
        "facts":          len(facts),
        "claims":         len(claims),
        "events":         len(events),
        "themes":         len(themes),
        "market_signals": len(market_signals),
        "object_links":   len(object_links) if isinstance(object_links, list) else 0,
        "memory_short_term": len(memory_context.get("relevant_short_term_memory") or []),
        "memory_watch":      len(memory_context.get("relevant_watch_memory") or []),
        "memory_long_term":  len(memory_context.get("relevant_long_term_memory") or []),
        "active_theses":     len(active_theses),
    }

    return {
        "entities":         entities,
        "facts":            facts,
        "claims":           claims,
        "events":           events,
        "themes":           themes,
        "market_signals":   market_signals,
        "object_links":     object_links,
        "memory_context":   memory_context,
        "active_theses":    active_theses,
        "entity_memory_map": entity_memory_map,
        "theme_memory_map":  theme_memory_map,
        "load_summary":     load_summary,
    }


def entity_names_from_event(event: dict) -> list[str]:
    """Extract string entity names from an event dict (handles list[str] and list[dict])."""
    raw = event.get("entities") or []
    names: list[str] = []
    for e in raw:
        if isinstance(e, str):
            names.append(e)
        elif isinstance(e, dict):
            n = e.get("entity_name") or e.get("name") or ""
            if n:
                names.append(n)
    return names
