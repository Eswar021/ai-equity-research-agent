"""
evidence_layer/text_chunker.py  —  Layer 8, Text Chunker

Chunks long text content (filings, transcripts) into fixed-size overlapping
windows for downstream retrieval. Used when vector_indexer is active (v2).

Design doc: docs/system_design_docs/layer_5.md (Evidence Builder section)
"""


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Stub — implement when vector store is added in v2."""
    raise NotImplementedError
