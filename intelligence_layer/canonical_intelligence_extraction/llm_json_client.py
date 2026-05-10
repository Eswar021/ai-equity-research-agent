"""
intelligence_layer/canonical_intelligence_extraction/llm_json_client.py — Layer 3

LangChain pipeline wrapper for Layer 3 LLM extraction calls.

Uses with_structured_output(DocumentExtractionResult) for guaranteed JSON.
Follows the same pattern as intelligence_layer/extraction/news_signal_extractor.py.

Design doc: docs/system_design_docs/layer_3.md §6 prompt_registry.py
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from langchain_core.prompts import ChatPromptTemplate

from intelligence_layer.canonical_intelligence_extraction.prompt_registry import (
    get_system_prompt,
    get_schema,
    get_batch_schema,
    DocumentExtractionResult,
    BatchExtractionResult,
)


def build_pipeline(llm, extraction_profile: str):
    """
    Build a LangChain pipeline for a given extraction profile.

    Returns a callable pipeline that takes {"text": str} and returns
    DocumentExtractionResult.

    Args:
        llm:               LangChain LLM (from llm.llm_client.make_llm)
        extraction_profile: key from prompt_registry (e.g. "news_extraction")
    """
    system_prompt = get_system_prompt(extraction_profile)
    schema        = get_schema()

    prompt   = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Source text:\n---\n{text}\n---\n\nExtract all intelligence objects. Return JSON only."),
    ])
    return prompt | llm.with_structured_output(schema)


def extract(pipeline, text: str) -> DocumentExtractionResult | None:
    """Run the pipeline on a single text chunk. Returns None on error."""
    try:
        return pipeline.invoke({"text": text})
    except Exception as e:
        print(f"  ✗  LLM extraction error: {e}")
        return None


def build_batch_pipeline(llm):
    """
    Build a pipeline for batch headline extraction.
    Packs N short docs into one LLM call using BatchExtractionResult schema.
    """
    system_prompt = get_system_prompt("batch_headline_extraction")
    schema        = get_batch_schema()
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Articles:\n---\n{text}\n---\n\nExtract from each article. Return JSON only."),
    ])
    return prompt | llm.with_structured_output(schema)


def extract_batch(batch_pipeline, text: str) -> BatchExtractionResult | None:
    """Run batch pipeline on combined headline text. Returns None on error."""
    try:
        return batch_pipeline.invoke({"text": text})
    except Exception as e:
        print(f"  ✗  Batch LLM extraction error: {e}")
        return None
