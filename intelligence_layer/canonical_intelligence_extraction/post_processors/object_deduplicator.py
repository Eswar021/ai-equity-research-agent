"""
intelligence_layer/canonical_intelligence_extraction/post_processors/object_deduplicator.py — Layer 3

Merges duplicate intelligence objects extracted from duplicate or near-duplicate documents.
Layer 2 deduplication removes duplicate source documents, but residual duplicates
(same event extracted from different article angles) still occur.

Dedup rules (design doc §20):
  Entities: same normalized entity_name → merge source_refs, keep highest confidence
  Events:   same (event_type, primary_entity, date_window) → merge source_refs
  Facts:    same (fact_type, primary_entity, metric_name, data_date) → merge
  Claims:   same (claim_text[:60] similarity) from same source within same date
  Themes:   theme_extractor.aggregate_themes() already handles this (called first)

Design doc: docs/system_design_docs/layer_3.md §20 object_deduplicator.py
"""

from __future__ import annotations
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_CLAIM_SIM_THRESHOLD = 0.88  # text similarity above this = same claim


def _norm(name: str) -> str:
    s = re.sub(r'\b(ltd|limited|pvt|corp|inc|co)\b', '', name.lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', s)).strip()


def _merge_source_refs(refs_a: list, refs_b: list) -> list:
    """Merge source_refs, deduplicating by document_id or record_id."""
    seen  = set()
    merged = []
    for ref in refs_a + refs_b:
        key = ref.get("document_id") or ref.get("record_id") or str(ref)
        if key not in seen:
            seen.add(key)
            merged.append(ref)
    return merged


def dedup_entities(entities: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Merge entities with the same normalized name.
    Returns (deduped_entities, dedup_map).
    """
    groups: dict[str, list[dict]] = {}
    for ent in entities:
        key = _norm(ent.get("entity_name", ""))
        groups.setdefault(key, []).append(ent)

    deduped = []
    dedup_map = []
    for norm_name, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        # Merge
        canonical = max(group, key=lambda e: e.get("confidence", 0.0))
        dup_ids   = [e["entity_id"] for e in group if e["entity_id"] != canonical["entity_id"]]
        for other in group:
            if other["entity_id"] == canonical["entity_id"]:
                continue
            canonical["source_refs"]  = _merge_source_refs(
                canonical.get("source_refs", []), other.get("source_refs", []))
            canonical["mention_count"] = canonical.get("mention_count", 1) + other.get("mention_count", 1)
            canonical["confidence"]    = max(canonical["confidence"], other.get("confidence", 0.0))
            # Merge aliases
            for alias in (other.get("aliases") or []):
                if alias and alias not in canonical.get("aliases", []):
                    canonical.setdefault("aliases", []).append(alias)

        deduped.append(canonical)
        if dup_ids:
            dedup_map.append({
                "canonical_object_id": canonical["entity_id"],
                "duplicate_object_ids": dup_ids,
                "reason": "same_normalized_entity_name",
            })

    return deduped, dedup_map


def dedup_events(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Merge events with same (event_type, primary entity name, date).
    """
    def _event_key(evt: dict) -> str:
        ents = evt.get("entities", [])
        primary = ents[0].get("entity_name", "") if ents else ""
        date    = evt.get("published_at", "")[:10]
        return f"{evt.get('event_type','')}__{_norm(primary)}__{date}"

    groups: dict[str, list[dict]] = {}
    for evt in events:
        key = _event_key(evt)
        groups.setdefault(key, []).append(evt)

    deduped   = []
    dedup_map = []
    for key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        canonical = max(group, key=lambda e: e.get("confidence", 0.0))
        dup_ids   = [e["event_id"] for e in group if e["event_id"] != canonical["event_id"]]
        for other in group:
            if other["event_id"] == canonical["event_id"]:
                continue
            canonical["source_refs"] = _merge_source_refs(
                canonical.get("source_refs", []), other.get("source_refs", []))
            canonical["confidence"]  = max(canonical["confidence"], other.get("confidence", 0.0))

        deduped.append(canonical)
        if dup_ids:
            dedup_map.append({
                "canonical_object_id":  canonical["event_id"],
                "duplicate_object_ids": dup_ids,
                "reason":               "same_entity_event_type_date",
            })

    return deduped, dedup_map


def dedup_facts(facts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge facts with same (fact_type, primary entity, metric_name, date)."""
    def _fact_key(f: dict) -> str:
        primary = f.get("entities", [""])[0] if f.get("entities") else ""
        metrics = f.get("metrics", [{}])
        metric  = metrics[0].get("metric_name", "") if metrics else ""
        date    = f.get("published_at", "")[:10]
        return f"{f.get('fact_type','')}__{_norm(primary)}__{metric}__{date}"

    groups: dict[str, list[dict]] = {}
    for fact in facts:
        groups.setdefault(_fact_key(fact), []).append(fact)

    deduped   = []
    dedup_map = []
    for _, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        canonical = max(group, key=lambda f: f.get("confidence", 0.0))
        dup_ids   = [f["fact_id"] for f in group if f["fact_id"] != canonical["fact_id"]]
        for other in group:
            if other["fact_id"] == canonical["fact_id"]:
                continue
            canonical["source_refs"] = _merge_source_refs(
                canonical.get("source_refs", []), other.get("source_refs", []))

        deduped.append(canonical)
        if dup_ids:
            dedup_map.append({
                "canonical_object_id":  canonical["fact_id"],
                "duplicate_object_ids": dup_ids,
                "reason":               "same_fact_type_entity_metric_date",
            })

    return deduped, dedup_map


def dedup_claims(claims: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge claims with very similar text from the same date."""
    deduped: list[dict]   = []
    dedup_map: list[dict] = []
    used: set[str]        = set()

    for i, claim_a in enumerate(claims):
        if claim_a["claim_id"] in used:
            continue
        dups = []
        for claim_b in claims[i + 1:]:
            if claim_b["claim_id"] in used:
                continue
            if claim_a.get("published_at", "")[:10] != claim_b.get("published_at", "")[:10]:
                continue
            sim = SequenceMatcher(
                None,
                claim_a.get("claim_text", "")[:80],
                claim_b.get("claim_text", "")[:80],
            ).ratio()
            if sim >= _CLAIM_SIM_THRESHOLD:
                dups.append(claim_b)
                used.add(claim_b["claim_id"])

        if dups:
            for other in dups:
                claim_a["source_refs"] = _merge_source_refs(
                    claim_a.get("source_refs", []), other.get("source_refs", []))
            dedup_map.append({
                "canonical_object_id":  claim_a["claim_id"],
                "duplicate_object_ids": [d["claim_id"] for d in dups],
                "reason":               "near_duplicate_claim_text",
            })
        deduped.append(claim_a)

    return deduped, dedup_map


def dedup_all(
    entities: list[dict],
    facts:    list[dict],
    claims:   list[dict],
    events:   list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """
    Dedup all object types. Returns (entities, facts, claims, events, full_dedup_map).
    """
    ents, em   = dedup_entities(entities)
    evts, evm  = dedup_events(events)
    fcts, fm   = dedup_facts(facts)
    clms, cm   = dedup_claims(claims)

    full_map = em + evm + fm + cm
    return ents, fcts, clms, evts, full_map
