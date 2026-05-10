"""
intelligence_layer/canonical_intelligence_extraction/post_processors/intelligence_object_linker.py — Layer 3

Links extracted intelligence objects together:
  event  → entity  (event affects entity)
  fact   → entity  (fact mentions entity)
  claim  → entity  (claim is about entity)
  theme  → event   (theme is supported_by event)
  theme  → claim   (theme is supported_by claim)

Links are built by normalized entity name matching — not deep NLP.
The output object_link_map is consumed by Layer 8 Evidence Builder.

Design doc: docs/system_design_docs/layer_3.md §17 intelligence_object_linker.py
"""

from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_LINK_COUNTER = [0]

def _next_link_id() -> str:
    _LINK_COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"LINK_{today}_{_LINK_COUNTER[0]:04d}"

def _norm(name: str) -> str:
    """Normalize entity name for matching: lowercase, drop Ltd/Limited/Corp etc."""
    s = re.sub(r'\b(ltd|limited|pvt|corp|corporation|inc|co)\b', '', name.lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).strip()


def link(
    entities: list[dict],
    facts:    list[dict],
    claims:   list[dict],
    events:   list[dict],
    themes:   list[dict],
    signals:  list[dict],
) -> list[dict]:
    """
    Build a link map between all intelligence objects.

    Returns:
        list of link dicts:
        {
          "link_id":            str,
          "from_object_type":   str,
          "from_object_id":     str,
          "to_object_type":     str,
          "to_object_id":       str,
          "relationship":       str,  # "affects" | "supported_by" | "mentions"
        }
    """
    # Build lookup: normalized entity name → entity_id
    entity_norm_to_id: dict[str, str] = {}
    for ent in entities:
        nname = _norm(ent.get("entity_name", ""))
        if nname:
            entity_norm_to_id[nname] = ent["entity_id"]
        # also add by ticker
        ticker = ent.get("ticker")
        if ticker:
            entity_norm_to_id[ticker.lower().replace(".ns", "")] = ent["entity_id"]

    links: list[dict] = []

    def _try_link(from_type, from_id, entity_names: list[str], rel: str):
        for name in entity_names:
            if not name:
                continue
            eid = entity_norm_to_id.get(_norm(name))
            if eid:
                links.append({
                    "link_id":          _next_link_id(),
                    "from_object_type": from_type,
                    "from_object_id":   from_id,
                    "to_object_type":   "entity",
                    "to_object_id":     eid,
                    "relationship":     rel,
                })

    # event → entity (affects)
    for evt in events:
        ent_names = [e.get("entity_name", "") if isinstance(e, dict) else e
                     for e in evt.get("entities", [])]
        _try_link("event", evt["event_id"], ent_names, "affects")

    # fact → entity (mentions)
    for fact in facts:
        _try_link("fact", fact["fact_id"], fact.get("entities", []), "mentions")

    # claim → entity (mentions)
    for claim in claims:
        _try_link("claim", claim["claim_id"], claim.get("entities", []), "mentions")

    # theme → events (supported_by): theme is related if it shares an entity with the event
    theme_entity_sets: list[tuple[str, set[str]]] = []
    for theme in themes:
        t_norms = {_norm(e) for e in theme.get("related_entities", []) if e}
        theme_entity_sets.append((theme["theme_id"], t_norms))

    for evt in events:
        evt_entity_names = [e.get("entity_name", "") if isinstance(e, dict) else e
                            for e in evt.get("entities", [])]
        evt_norms = {_norm(n) for n in evt_entity_names if n}

        for theme_id, t_norms in theme_entity_sets:
            if t_norms & evt_norms:  # overlap
                links.append({
                    "link_id":          _next_link_id(),
                    "from_object_type": "theme",
                    "from_object_id":   theme_id,
                    "to_object_type":   "event",
                    "to_object_id":     evt["event_id"],
                    "relationship":     "supported_by",
                })

        # Also update theme.related_events in-place
        for theme in themes:
            t_norms2 = {_norm(e) for e in theme.get("related_entities", []) if e}
            if t_norms2 & evt_norms and evt["event_id"] not in theme.get("related_events", []):
                theme.setdefault("related_events", []).append(evt["event_id"])

    # theme → claims (supported_by)
    for claim in claims:
        claim_norms = {_norm(e) for e in claim.get("entities", []) if e}
        for theme in themes:
            t_norms = {_norm(e) for e in theme.get("related_entities", []) if e}
            if t_norms & claim_norms:
                links.append({
                    "link_id":          _next_link_id(),
                    "from_object_type": "theme",
                    "from_object_id":   theme["theme_id"],
                    "to_object_type":   "claim",
                    "to_object_id":     claim["claim_id"],
                    "relationship":     "supported_by",
                })

    return links
