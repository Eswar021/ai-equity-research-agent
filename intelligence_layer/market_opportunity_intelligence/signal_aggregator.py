"""
intelligence_layer/market_opportunity_intelligence/signal_aggregator.py — Layer 5

Groups the 1700+ Layer 3 objects into ~30-50 named signal groups.
Downstream agents reason over signal groups, not raw objects.

Grouping strategy:
  1. Theme-centric groups  — one per unique theme (themes are pre-named anchors)
  2. Entity-centric groups — for events that have no matching theme
  3. Market signal group   — all institutional_flow / macro / derivatives signals together

Each group carries: entities, event_ids, fact_ids, claim_ids, memory_refs,
source_diversity_count, recurrence_level, confidence.

Design doc: docs/system_design_docs/layer_5.md §3 signal_aggregator.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from intelligence_layer.market_opportunity_intelligence.intelligence_memory_loader import (
    entity_names_from_event,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def aggregate(intelligence: dict) -> list[dict]:
    """
    Build signal groups from the loaded intelligence dict.

    Returns list of signal_group dicts.
    """
    themes         = intelligence.get("themes") or []
    events         = intelligence.get("events") or []
    facts          = intelligence.get("facts") or []
    claims         = intelligence.get("claims") or []
    market_signals = intelligence.get("market_signals") or []
    entity_mem_map = intelligence.get("entity_memory_map") or {}
    theme_mem_map  = intelligence.get("theme_memory_map") or {}

    groups: list[dict] = []
    assigned_event_ids: set[str] = set()

    # ── 1. Theme-centric groups ───────────────────────────────────────────────
    for theme in themes:
        theme_name     = theme.get("theme_name", "")
        theme_entities = {e.lower() for e in (theme.get("related_entities") or [])}
        theme_id       = theme.get("theme_id", "")

        matched_events  = _match_events_by_entities(events, theme_entities)
        matched_facts   = _match_by_entities(facts, theme_entities)
        matched_claims  = _match_by_entities(claims, theme_entities)

        for eid in matched_events:
            assigned_event_ids.add(eid)

        mem_refs = _memory_refs(theme_entities, {theme_name.lower()},
                                entity_mem_map, theme_mem_map)
        rec_level = _recurrence_level(mem_refs, intelligence)

        grp = _make_group(
            group_type    = "theme_centric",
            theme_name    = theme_name,
            theme_id      = theme_id,
            theme_type    = theme.get("theme_type", ""),
            entities      = list(theme_entities),
            event_ids     = list(matched_events.keys()),
            events_detail = list(matched_events.values()),
            fact_ids      = [f["fact_id"] for f in matched_facts],
            claim_ids     = [c["claim_id"] for c in matched_claims],
            market_signal_ids = [],
            memory_refs   = mem_refs,
            recurrence_level = rec_level,
            source_refs   = _collect_source_refs(
                list(matched_events.values()), matched_facts, matched_claims, [theme]
            ),
            confidence    = theme.get("confidence", 0.5),
            mention_count = theme.get("mention_count", 1),
        )
        groups.append(grp)

    # ── 2. Entity-centric groups for unassigned events ────────────────────────
    unassigned = [e for e in events if e.get("event_id") not in assigned_event_ids]
    entity_event_map: dict[str, list[dict]] = {}
    for evt in unassigned:
        names = entity_names_from_event(evt)
        anchor = names[0].lower() if names else "unknown"
        entity_event_map.setdefault(anchor, []).append(evt)

    for anchor_entity, evts in entity_event_map.items():
        evt_entities = {anchor_entity}
        for evt in evts:
            for n in entity_names_from_event(evt):
                evt_entities.add(n.lower())

        matched_facts  = _match_by_entities(facts, evt_entities)
        matched_claims = _match_by_entities(claims, evt_entities)
        mem_refs       = _memory_refs(evt_entities, set(), entity_mem_map, theme_mem_map)
        rec_level      = _recurrence_level(mem_refs, intelligence)

        evt_ids     = {e["event_id"]: e for e in evts}
        grp = _make_group(
            group_type    = "entity_centric",
            theme_name    = anchor_entity,
            theme_id      = "",
            theme_type    = "",
            entities      = list(evt_entities),
            event_ids     = list(evt_ids.keys()),
            events_detail = list(evt_ids.values()),
            fact_ids      = [f["fact_id"] for f in matched_facts],
            claim_ids     = [c["claim_id"] for c in matched_claims],
            market_signal_ids = [],
            memory_refs   = mem_refs,
            recurrence_level = rec_level,
            source_refs   = _collect_source_refs(evts, matched_facts, matched_claims, []),
            confidence    = max((e.get("confidence", 0.5) for e in evts), default=0.5),
            mention_count = len(evts),
        )
        groups.append(grp)

    # ── 3. Market signal group ────────────────────────────────────────────────
    if market_signals:
        sig_src_refs = []
        for sig in market_signals:
            sig_src_refs.extend(sig.get("source_refs") or [])
        grp = _make_group(
            group_type    = "market_signal",
            theme_name    = "market_flows_and_macro",
            theme_id      = "",
            theme_type    = "macro_theme",
            entities      = [],
            event_ids     = [],
            events_detail = [],
            fact_ids      = [],
            claim_ids     = [],
            market_signal_ids = [s["signal_id"] for s in market_signals],
            market_signals_detail = market_signals,
            memory_refs   = [],
            recurrence_level = "new",
            source_refs   = sig_src_refs[:20],
            confidence    = 0.85,
            mention_count = len(market_signals),
        )
        groups.append(grp)

    return groups


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_group(group_type: str, theme_name: str, theme_id: str,
                theme_type: str, entities: list, event_ids: list,
                events_detail: list, fact_ids: list, claim_ids: list,
                market_signal_ids: list, memory_refs: list,
                recurrence_level: str, source_refs: list,
                confidence: float, mention_count: int,
                market_signals_detail: list | None = None) -> dict:
    _CTR[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    src_ids = {r.get("source_id") or r.get("document_id") or "" for r in source_refs if r}

    return {
        "signal_group_id":      f"SIGGRP_{today}_{_CTR[0]:04d}",
        "group_type":           group_type,
        "theme":                theme_name,
        "theme_id":             theme_id,
        "theme_type":           theme_type,
        "entities":             entities,
        "event_ids":            event_ids,
        "events_detail":        events_detail,
        "fact_ids":             fact_ids,
        "claim_ids":            claim_ids,
        "market_signal_ids":    market_signal_ids,
        "market_signals_detail": market_signals_detail or [],
        "memory_refs":          memory_refs,
        "source_refs":          source_refs[:10],
        "source_diversity_count": len(src_ids - {""}),
        "recurrence_level":     recurrence_level,
        "confidence":           round(confidence, 3),
        "mention_count":        mention_count,
    }


def _match_events_by_entities(events: list[dict],
                               theme_entities: set[str]) -> dict[str, dict]:
    """Return {event_id: event} for events sharing ≥1 entity with the theme."""
    matched: dict[str, dict] = {}
    for evt in events:
        evt_names = {n.lower() for n in entity_names_from_event(evt)}
        if evt_names & theme_entities:
            matched[evt["event_id"]] = evt
    return matched


def _match_by_entities(objects: list[dict], theme_entities: set[str]) -> list[dict]:
    """Match facts or claims by their entities field (list[str])."""
    result: list[dict] = []
    for obj in objects:
        obj_entities = {e.lower() for e in (obj.get("entities") or [])}
        if obj_entities & theme_entities:
            result.append(obj)
    return result


def _memory_refs(entities: set[str], themes: set[str],
                 entity_mem_map: dict, theme_mem_map: dict) -> list[str]:
    refs: list[str] = []
    for e in entities:
        for mid in (entity_mem_map.get(e) or []):
            if mid not in refs:
                refs.append(mid)
    for t in themes:
        for mid in (theme_mem_map.get(t) or []):
            if mid not in refs:
                refs.append(mid)
    return refs[:5]


def _recurrence_level(memory_refs: list[str], intelligence: dict) -> str:
    if not memory_refs:
        return "new"
    mem_ctx    = intelligence.get("memory_context") or {}
    watch      = mem_ctx.get("relevant_watch_memory") or []
    long_term  = mem_ctx.get("relevant_long_term_memory") or []
    watch_ids  = {r.get("memory_id") for r in watch}
    lt_ids     = {r.get("memory_id") for r in long_term}
    ref_set    = set(memory_refs)
    if ref_set & lt_ids:
        return "high_recurring"
    if ref_set & watch_ids:
        return "recurring"
    return "new_with_memory"


def _collect_source_refs(events: list[dict], facts: list[dict],
                         claims: list[dict], themes: list[dict]) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for obj in events + facts + claims + themes:
        for r in (obj.get("source_refs") or []):
            key = r.get("source_id") or r.get("document_id") or ""
            if key and key not in seen:
                seen.add(key)
                refs.append(r)
    return refs[:15]
