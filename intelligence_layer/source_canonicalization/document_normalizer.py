"""
intelligence_layer/source_canonicalization/document_normalizer.py  —  Layer 2, Document Normalizer

Normalizes raw documents from all Layer 1 collectors into a canonical
CanonicalDocument schema: strips HTML, standardises fields, sets language.

Design doc: docs/system_design_docs/layer_2.md
"""


def normalize(raw_doc: dict) -> dict:
    """Returns canonical doc dict. Stub — implement per layer_2 design doc."""
    raise NotImplementedError
