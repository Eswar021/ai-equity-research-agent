"""
intelligence_layer/canonical_intelligence_extraction/extractors/fact_extractor.py — Layer 3

Formats fact items from LLM output into canonical fact card objects.
Facts are verifiable statements — not opinions or forecasts.

Design doc: docs/system_design_docs/layer_3.md §8 fact_extractor.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_fact_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"FACT_{today}_{_COUNTER[0]:04d}"


def format_facts(
    llm_facts: list,   # list[FactItem]
    document:  dict,
    chunk:     dict,
) -> list[dict]:
    """
    Convert raw LLM fact items into canonical fact card objects.

    Returns:
        list of fact card dicts matching design doc fact card schema.
    """
    doc_id      = document.get("document_id", "")
    source_id   = (document.get("lineage") or {}).get("source_module", "")
    reliability = document.get("source_reliability", "medium")
    published   = document.get("published_at", "")

    facts = []
    for item in llm_facts:
        fact_id = _next_fact_id()

        # Build metrics list only if metric data is present
        metrics = []
        if item.metric_name:
            metrics.append({
                "metric_name":  item.metric_name,
                "metric_value": item.metric_value,
                "unit":         item.unit,
            })

        facts.append({
            "fact_id":       fact_id,
            "fact_type":     item.fact_type,
            "fact_text":     item.fact_text.strip(),
            "entities":      [e.strip() for e in item.entities if e.strip()],
            "metrics":       metrics,
            "source_refs": [{
                "document_id":       doc_id,
                "source_id":         source_id,
                "chunk_id":          chunk.get("chunk_id", ""),
                "supporting_text":   item.supporting_text or "",
                "published_at":      published,
                "source_reliability": reliability,
            }],
            "published_at":  published,
            "confidence":    max(0.0, min(1.0, float(item.confidence))),
        })
    return facts
