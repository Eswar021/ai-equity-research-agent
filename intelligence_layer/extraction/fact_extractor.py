"""
intelligence_layer/extraction/fact_extractor.py  —  Layer 3, Fact Extractor

Thin wrapper around canonical_intelligence_extraction pipeline.
Routes, chunks, runs LLM extraction, and formats fact objects for one document.

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
from intelligence_layer.canonical_intelligence_extraction.extractors.fact_extractor import format_facts


def extract_facts(doc: dict, llm) -> list[dict]:
    """
    Extract fact objects from a single canonical document.

    Runs the full mini-pipeline: route → chunk → LLM extraction → format.
    Returns [] if document is skipped or LLM fails.

    For batch processing use layer3_runner.run() instead.
    """
    routing = route(doc)
    if routing["skip"]:
        return []

    pipeline = llm_json_client.build_pipeline(llm, routing["extraction_profile"])
    chunks   = chunk_doc(doc, routing)
    facts    = []
    for chunk in chunks:
        result = llm_json_client.extract(pipeline, chunk["text"])
        if result is not None:
            facts.extend(format_facts(result.facts, doc, chunk))
    return facts
