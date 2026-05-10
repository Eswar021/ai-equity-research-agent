"""
intelligence_layer/extraction/theme_extractor.py  —  Layer 3, Theme Extractor

Thin wrapper around canonical_intelligence_extraction pipeline.
Routes, chunks, runs LLM extraction, and formats theme objects for one document.
Cross-document aggregation is available via aggregate_themes().

Full multi-document pipeline: use layer3_runner.run() instead.

Design doc: docs/system_design_docs/layer_3.md
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from intelligence_layer.canonical_intelligence_extraction.document_router import route
from intelligence_layer.canonical_intelligence_extraction.extraction_chunker import chunk as chunk_doc
from intelligence_layer.canonical_intelligence_extraction import llm_json_client
from intelligence_layer.canonical_intelligence_extraction.extractors.theme_extractor import (
    format_themes,
    aggregate_themes,
)


def extract_themes(doc: dict, llm) -> list[dict]:
    """
    Extract raw per-document theme objects from a single canonical document.

    Returns unaggregated themes. Call aggregate_themes(raw_themes) after
    collecting across all documents to produce final cross-document theme cards.

    For batch processing use layer3_runner.run() instead.
    """
    routing = route(doc)
    if routing["skip"]:
        return []

    pipeline   = llm_json_client.build_pipeline(llm, routing["extraction_profile"])
    chunks     = chunk_doc(doc, routing)
    raw_themes: list[dict] = []
    for chunk in chunks:
        result = llm_json_client.extract(pipeline, chunk["text"])
        if result is not None:
            raw_themes.extend(format_themes(result.themes, doc, chunk))
    return raw_themes


__all__ = ["extract_themes", "aggregate_themes"]
