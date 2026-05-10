"""
intelligence_layer/canonical_intelligence_extraction/extractors/entity_extractor.py — Layer 3

Formats entity items from the LLM's DocumentExtractionResult into canonical
entity objects with stable IDs and source_refs.

Does NOT make LLM calls. Receives already-parsed LLM output from the runner.

Design doc: docs/system_design_docs/layer_3.md §7 entity_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_COUNTER = [0]

def _next_entity_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"ENT_{today}_{_COUNTER[0]:04d}"


def format_entities(
    llm_entities: list,       # list[EntityItem] from DocumentExtractionResult
    document:     dict,       # canonical_document being processed
    chunk:        dict,       # chunk dict from extraction_chunker
) -> list[dict]:
    """
    Convert raw LLM entity items into canonical entity objects.

    Args:
        llm_entities: list of EntityItem Pydantic objects
        document:     canonical_document dict
        chunk:        chunk dict (for source_refs supporting_text)

    Returns:
        list of entity dicts matching the design doc entity object schema.
    """
    doc_id      = document.get("document_id", "")
    source_id   = (document.get("lineage") or {}).get("source_module", "")
    reliability = document.get("source_reliability", "medium")
    published   = document.get("published_at", "")

    entities = []
    for item in llm_entities:
        entity_id = _next_entity_id()
        entities.append({
            "entity_id":        entity_id,
            "entity_name":      item.entity_name.strip(),
            "normalized_name":  item.entity_name.strip().title(),
            "entity_type":      item.entity_type,
            "market_status":    "listed" if item.entity_type == "listed_company" else "unlisted",
            "ticker":           None,           # filled by entity_resolver_light
            "ticker_hint":      item.ticker_hint,
            "exchange":         None,
            "country":          "India" if item.market in ("india",) else None,
            "market":           item.market,
            "aliases":          [],
            "resolution_status": "pending",     # filled by entity_resolver_light
            "source_refs": [{
                "document_id":    doc_id,
                "source_id":      source_id,
                "chunk_id":       chunk.get("chunk_id", ""),
                "supporting_text": item.supporting_text or "",
                "published_at":   published,
                "source_reliability": reliability,
            }],
            "mention_count":   1,
            "confidence":      max(0.0, min(1.0, float(item.confidence))),
        })
    return entities
