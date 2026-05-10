"""
intelligence_layer/canonical_intelligence_extraction/extraction_chunker.py — Layer 3

Temporarily splits long canonical documents into chunks for LLM extraction.
This is NOT vector DB chunking (that belongs to Layer 8). These chunks exist
only during a single Layer 3 extraction run and are discarded afterward.

Chunking strategies (design doc §5):
  - none:               return full text as single chunk (short docs / rss)
  - sentence_boundary:  split at sentence ends, respecting max_chunk_chars
  - speaker:            split at speaker-change lines (transcripts)
  - heading:            split at Markdown-style headings (filings/presentations)

Design doc: docs/system_design_docs/layer_3.md §5 extraction_chunker.py
"""

from __future__ import annotations
import re

_DEFAULT_MAX_CHARS = 3_500
_MIN_CHUNK_CHARS   = 200   # don't create a chunk shorter than this


def chunk(
    document: dict,
    routing:  dict,
) -> list[dict]:
    """
    Split a document into extraction chunks based on its routing profile.

    Args:
        document: canonical_document dict (must have clean_text or body)
        routing:  routing_decision dict from document_router.route()

    Returns:
        list of chunk dicts:
        {
          "chunk_id":     str,   e.g. "DOC_001_C01"
          "chunk_index":  int,   1-based
          "total_chunks": int,
          "section":      str,   "full" | "chunk_N" | speaker name | heading title
          "start_offset": int,
          "end_offset":   int,
          "text":         str,
        }
    """
    doc_id       = document.get("document_id", "DOC")
    raw_text     = document.get("clean_text") or document.get("body") or ""
    strategy     = routing.get("chunk_strategy", "sentence_boundary")
    max_chars    = routing.get("max_chunk_chars", _DEFAULT_MAX_CHARS)

    if not raw_text:
        return []

    if strategy == "none" or len(raw_text) <= max_chars:
        return [_make_chunk(doc_id, raw_text, 1, 1, "full", 0, len(raw_text))]

    if strategy == "speaker":
        segments = _split_by_speaker(raw_text, max_chars)
    elif strategy == "heading":
        segments = _split_by_heading(raw_text, max_chars)
    else:  # sentence_boundary (default)
        segments = _split_by_sentence(raw_text, max_chars)

    total = len(segments)
    chunks = []
    for idx, (text, section, start, end) in enumerate(segments, start=1):
        chunks.append(_make_chunk(doc_id, text, idx, total, section, start, end))
    return chunks


def _make_chunk(doc_id, text, idx, total, section, start, end) -> dict:
    return {
        "chunk_id":     f"{doc_id}_C{idx:02d}",
        "chunk_index":  idx,
        "total_chunks": total,
        "section":      section,
        "start_offset": start,
        "end_offset":   end,
        "text":         text,
    }


def _split_by_sentence(text: str, max_chars: int) -> list[tuple]:
    """Split at sentence boundaries (. ! ?), keeping chunks ≤ max_chars."""
    sentences  = re.split(r'(?<=[.!?])\s+', text)
    segments   = []
    current    = []
    cur_len    = 0
    offset     = 0
    chunk_start = 0

    for sent in sentences:
        if cur_len + len(sent) > max_chars and current:
            seg_text = " ".join(current)
            segments.append((seg_text, f"chunk_{len(segments)+1}", chunk_start, chunk_start + len(seg_text)))
            chunk_start += len(seg_text) + 1
            current, cur_len = [], 0
        current.append(sent)
        cur_len += len(sent) + 1

    if current:
        seg_text = " ".join(current)
        segments.append((seg_text, f"chunk_{len(segments)+1}", chunk_start, chunk_start + len(seg_text)))

    return segments if segments else [(text[:max_chars], "chunk_1", 0, min(max_chars, len(text)))]


def _split_by_speaker(text: str, max_chars: int) -> list[tuple]:
    """
    Split at speaker-change lines.
    Speaker lines match patterns like "Analyst:", "CEO:", "Q:", "A:", or
    lines in ALL CAPS followed by colon.
    Falls back to sentence_boundary if no speaker markers found.
    """
    speaker_re = re.compile(r'^(?:[A-Z][A-Za-z\s\-\.]+:|Q:|A:)\s*', re.MULTILINE)
    boundaries = [m.start() for m in speaker_re.finditer(text)]

    if not boundaries:
        return _split_by_sentence(text, max_chars)

    segments = []
    for i, start in enumerate(boundaries):
        end      = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        seg_text = text[start:end].strip()

        # speaker label is the first line
        first_line = seg_text.split("\n", 1)[0][:60]

        if len(seg_text) <= max_chars:
            segments.append((seg_text, first_line, start, end))
        else:
            # speaker segment itself is too long — sub-chunk by sentence
            sub = _split_by_sentence(seg_text, max_chars)
            for j, (st, _, ss, se) in enumerate(sub):
                segments.append((st, f"{first_line}_part{j+1}", start + ss, start + se))

    return segments if segments else [(text[:max_chars], "chunk_1", 0, min(max_chars, len(text)))]


def _split_by_heading(text: str, max_chars: int) -> list[tuple]:
    """
    Split at Markdown headings (# / ## / ###) or ALL-CAPS lines as headings.
    Falls back to sentence_boundary if no headings found.
    """
    heading_re = re.compile(r'^(?:#{1,4}\s+.+|[A-Z][A-Z\s]{4,})', re.MULTILINE)
    boundaries = [m.start() for m in heading_re.finditer(text)]

    if not boundaries:
        return _split_by_sentence(text, max_chars)

    segments = []
    for i, start in enumerate(boundaries):
        end      = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        seg_text = text[start:end].strip()
        heading  = text[start:start + 80].split("\n", 1)[0].strip("#").strip()[:60]

        if len(seg_text) <= max_chars:
            segments.append((seg_text, heading, start, end))
        else:
            sub = _split_by_sentence(seg_text, max_chars)
            for j, (st, _, ss, se) in enumerate(sub):
                segments.append((st, f"{heading}_part{j+1}", start + ss, start + se))

    return segments if segments else [(text[:max_chars], "chunk_1", 0, min(max_chars, len(text)))]
