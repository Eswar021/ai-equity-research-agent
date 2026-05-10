"""
intelligence_layer/canonical_intelligence_extraction/extractors/event_extractor.py — Layer 3

Formats event items from LLM output into canonical event card objects.
Events are discrete, investment-relevant things that happened or were announced.

Design doc: docs/system_design_docs/layer_3.md §10 event_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_event_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"EVT_{today}_{_COUNTER[0]:04d}"


def format_events(
    llm_events: list,   # list[EventItem]
    document:   dict,
    chunk:      dict,
) -> list[dict]:
    """
    Convert raw LLM event items into canonical event card objects.

    Returns:
        list of event card dicts matching design doc event card schema.
    """
    doc_id      = document.get("document_id", "")
    source_id   = (document.get("lineage") or {}).get("source_module", "")
    reliability = document.get("source_reliability", "medium")
    published   = document.get("published_at", "")

    events = []
    for item in llm_events:
        event_id = _next_event_id()

        # Build entities list (design doc format: list of {entity_name, entity_type, ticker})
        entities = []
        for e in item.entities:
            if isinstance(e, str):
                entities.append({
                    "entity_name": e.strip(),
                    "entity_type": "unknown",
                    "ticker":      None,       # filled by entity_resolver_light
                })
            elif isinstance(e, dict):
                entities.append(e)

        events.append({
            "event_id":                      event_id,
            "event_type":                    item.event_type,
            "event_title":                   item.event_title.strip(),
            "event_summary":                 item.event_summary.strip(),
            "entities":                      entities,
            "impact_scope":                  list(item.impact_scope),
            "initial_sentiment":             item.initial_sentiment,
            "business_impact":               item.business_impact,
            "severity":                      item.severity,
            "time_horizon":                  item.time_horizon,
            "temporary_or_structural_hint":  item.temporary_or_structural_hint,
            "source_refs": [{
                "document_id":       doc_id,
                "source_id":         source_id,
                "chunk_id":          chunk.get("chunk_id", ""),
                "supporting_text":   item.supporting_text or "",
                "published_at":      published,
                "source_reliability": reliability,
            }],
            "source_reliability": reliability,
            "published_at":       published,
            "confidence":         max(0.0, min(1.0, float(item.confidence))),
        })
    return events
