"""
intelligence_layer/canonical_intelligence_extraction/extractors/theme_extractor.py — Layer 3

Two-level theme extraction (design doc §11):

  Level 1 — per-document:
    format_themes() formats LLM-extracted theme items into canonical theme objects.
    These represent themes the LLM identified in a single document.

  Level 2 — cross-document aggregation:
    aggregate_themes() groups all per-document themes across the entire run.
    Themes that appear in multiple documents from multiple sources are stronger signals.
    This is what actually builds the theme_cards.json output.

Design doc: docs/system_design_docs/layer_3.md §11 theme_extractor.py
"""

from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_COUNTER = [0]

def _next_theme_id() -> str:
    _COUNTER[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"THEME_{today}_{_COUNTER[0]:04d}"


def _normalize_theme_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for dedup grouping."""
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', name.lower())).strip()


def format_themes(
    llm_themes: list,   # list[ThemeItem]
    document:   dict,
    chunk:      dict,
) -> list[dict]:
    """
    Level 1: Convert raw LLM theme items from a single document into theme objects.

    These are raw per-document theme observations, not yet the final aggregated themes.
    """
    doc_id    = document.get("document_id", "")
    source_id = (document.get("lineage") or {}).get("source_module", "")
    published = document.get("published_at", "")

    themes = []
    for item in llm_themes:
        theme_id = _next_theme_id()
        themes.append({
            "theme_id":         theme_id,
            "theme_name":       item.theme_name.strip(),
            "normalized_name":  _normalize_theme_name(item.theme_name),
            "theme_type":       item.theme_type,
            "description":      item.description.strip(),
            "related_entities": [e.strip() for e in item.related_entities if e.strip()],
            "related_events":   [],          # filled by intelligence_object_linker
            "source_refs": [{
                "document_id":  doc_id,
                "source_id":    source_id,
                "chunk_id":     chunk.get("chunk_id", ""),
                "published_at": published,
            }],
            "mention_count":         1,
            "source_diversity_count": 1,
            "time_horizon_hint":      item.time_horizon_hint,
            "confidence":            max(0.0, min(1.0, float(item.confidence))),
        })
    return themes


def aggregate_themes(raw_themes: list[dict]) -> list[dict]:
    """
    Level 2: Group raw per-document themes by normalized name.

    Themes with the same normalized name are merged:
    - mention_count sums up
    - source_diversity_count counts distinct document IDs
    - related_entities are merged (deduplicated)
    - source_refs are combined
    - confidence uses the max of individual confidences
    - description uses the longest/most informative one

    Returns final theme_cards list.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in raw_themes:
        key = t.get("normalized_name", "")
        if key:
            groups[key].append(t)

    aggregated = []
    for norm_name, group in groups.items():
        # Use the theme entry with the highest confidence as the base
        base = max(group, key=lambda x: x.get("confidence", 0.0))

        # Merge source_refs and entities
        all_refs    = []
        all_entities = []
        all_doc_ids  = set()
        for t in group:
            all_refs.extend(t.get("source_refs", []))
            all_entities.extend(t.get("related_entities", []))
            for ref in t.get("source_refs", []):
                if ref.get("document_id"):
                    all_doc_ids.add(ref["document_id"])

        # Deduplicate entities (case-insensitive)
        seen_ents = set()
        merged_entities = []
        for e in all_entities:
            if e.lower() not in seen_ents:
                seen_ents.add(e.lower())
                merged_entities.append(e)

        # Use the longest description
        best_description = max((t.get("description", "") for t in group), key=len)
        max_conf = max(t.get("confidence", 0.0) for t in group)

        aggregated.append({
            "theme_id":              base["theme_id"],
            "theme_name":            base["theme_name"],
            "normalized_name":       norm_name,
            "theme_type":            base.get("theme_type", "other"),
            "description":           best_description,
            "related_entities":      merged_entities,
            "related_events":        [],        # filled by intelligence_object_linker
            "source_refs":           all_refs,
            "mention_count":         len(group),
            "source_diversity_count": len(all_doc_ids),
            "time_horizon_hint":     base.get("time_horizon_hint", "unknown"),
            "confidence":            max_conf,
        })

    # Sort by mention_count descending (strongest themes first)
    aggregated.sort(key=lambda x: x["mention_count"], reverse=True)
    return aggregated
