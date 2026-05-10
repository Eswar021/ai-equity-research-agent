"""
intelligence_layer/extraction/event_extractor.py  —  Layer 3, Event Extractor

Thin wrapper around canonical_intelligence_extraction pipeline.
Routes, chunks, runs LLM extraction, and formats event objects for one document.

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
from intelligence_layer.canonical_intelligence_extraction.extractors.event_extractor import format_events


def extract_events(doc: dict, llm) -> list[dict]:
    """
    Extract event objects from a single canonical document.

    Runs the full mini-pipeline: route → chunk → LLM extraction → format.
    Returns [] if document is skipped or LLM fails.

    For batch processing use layer3_runner.run() instead.
    """
    routing = route(doc)
    if routing["skip"]:
        return []

    pipeline = llm_json_client.build_pipeline(llm, routing["extraction_profile"])
    chunks   = chunk_doc(doc, routing)
    events   = []
    for chunk in chunks:
        result = llm_json_client.extract(pipeline, chunk["text"])
        if result is not None:
            events.extend(format_events(result.events, doc, chunk))
    return events
