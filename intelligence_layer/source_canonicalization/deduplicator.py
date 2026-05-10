"""
intelligence_layer/source_canonicalization/deduplicator.py — Layer 2

Detects exact and near-exact duplicate canonical_documents. Structured
records are not deduplicated (each ticker/module pair is unique by design).

Exact duplicate detection (design doc §24):
  - same normalized URL  (url_hash collision)
  - same content_hash    (identical body text)

Near-duplicate detection:
  - same title_hash AND same publisher AND same data_date
  - OR title similarity > 0.85 from difflib on same publisher+date
    (covers headline rephrasing between MC / ET / RSS for the same story)

Simhash is deferred — URL + content_hash already covers the vast majority
of real duplicates in Indian finance sources.

Design doc: docs/system_design_docs/layer_2.md  §24 deduplicator.py
"""

from __future__ import annotations
from difflib import SequenceMatcher


_NEAR_DUP_TITLE_THRESHOLD = 0.85   # title similarity above this = near duplicate


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _doc_date(doc: dict) -> str:
    """Extract YYYY-MM-DD from published_at for grouping."""
    pub = doc.get("published_at") or ""
    return str(pub)[:10] if pub else ""


def deduplicate(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Detect and mark duplicates in a list of canonical_documents.

    Args:
        documents: list of canonical_document dicts with 'fingerprint' key.

    Returns:
        (deduplicated_docs, duplicate_groups)

        deduplicated_docs:
            Same list but with duplicate_status populated. Duplicate documents
            are kept (not discarded) — they are marked is_duplicate=True.
            Later layers should filter on canonical_document_for_group=True.

        duplicate_groups:
            [{ "duplicate_group_id": str,
               "canonical_document_id": str,
               "duplicate_document_ids": [str],
               "reason": str }]

    Design doc output schema: §24.
    """
    seen_url:     dict[str, str] = {}   # url_hash     → document_id
    seen_content: dict[str, str] = {}   # content_hash → document_id
    # (publisher, date, title_hash) → document_id  for near-dedup
    seen_near:    dict[tuple, str] = {}

    groups:  list[dict] = []
    _group_counter = [0]

    def _new_group_id() -> str:
        _group_counter[0] += 1
        return f"DUPGRP_{_group_counter[0]:04d}"

    def _mark_duplicate(doc: dict, canonical_id: str, group_id: str, reason: str):
        doc["duplicate_status"] = {
            "is_duplicate":              True,
            "duplicate_group_id":        group_id,
            "canonical_document_for_group": False,
            "duplicate_of":              canonical_id,
            "reason":                    reason,
        }

    def _find_or_create_group(canonical_id: str, reason: str) -> str:
        """Find existing group for canonical_id or create a new one."""
        for g in groups:
            if g["canonical_document_id"] == canonical_id:
                return g["duplicate_group_id"]
        gid = _new_group_id()
        groups.append({
            "duplicate_group_id":    gid,
            "canonical_document_id": canonical_id,
            "duplicate_document_ids": [],
            "reason":                reason,
        })
        return gid

    def _add_to_group(group_id: str, dup_id: str):
        for g in groups:
            if g["duplicate_group_id"] == group_id:
                if dup_id not in g["duplicate_document_ids"]:
                    g["duplicate_document_ids"].append(dup_id)
                return

    for idx, doc in enumerate(documents):
        doc_id = doc.get("document_id", "")
        fp     = doc.get("fingerprint") or {}
        url_h  = fp.get("url_hash", "")
        cnt_h  = fp.get("content_hash", "")
        ttl_h  = fp.get("title_hash", "")
        pub    = (doc.get("publisher") or doc.get("source_name") or "").lower()
        date   = _doc_date(doc)

        dup_found   = False
        canon_id    = ""
        dup_reason  = ""

        # 1. Exact URL dedup
        if url_h and url_h in seen_url:
            canon_id   = seen_url[url_h]
            dup_reason = "same_url"
            dup_found  = True

        # 2. Exact content dedup (only if body is non-trivial)
        elif cnt_h and cnt_h in seen_content and len(doc.get("clean_text", "")) > 100:
            canon_id   = seen_content[cnt_h]
            dup_reason = "same_content_hash"
            dup_found  = True

        # 3. Near-dedup: same title_hash + same publisher + same date
        elif ttl_h and date and pub:
            near_key = (pub, date, ttl_h)
            if near_key in seen_near:
                canon_id   = seen_near[near_key]
                dup_reason = "same_title_publisher_date"
                dup_found  = True

        # 4. Near-dedup: high title similarity — only look at already-processed docs
        #    (docs[:idx]) to avoid marking doc1 as a duplicate of a future doc2.
        if not dup_found and date and pub and doc.get("title"):
            title_a = doc.get("title", "")
            for candidate in documents[:idx]:
                if candidate.get("duplicate_status", {}).get("is_duplicate"):
                    continue   # skip candidates that are themselves duplicates
                if (candidate.get("publisher", "").lower() == pub
                        and _doc_date(candidate) == date
                        and candidate.get("title")):
                    sim = _title_similarity(title_a, candidate["title"])
                    if sim >= _NEAR_DUP_TITLE_THRESHOLD:
                        canon_id   = candidate.get("document_id", "")
                        dup_reason = f"near_duplicate_title_similarity_{sim:.2f}"
                        dup_found  = True
                        break

        if dup_found and canon_id:
            gid = _find_or_create_group(canon_id, dup_reason)
            _mark_duplicate(doc, canon_id, gid, dup_reason)
            _add_to_group(gid, doc_id)
        else:
            # Not a duplicate — register fingerprints
            if url_h:
                seen_url[url_h] = doc_id
            if cnt_h and len(doc.get("clean_text", "")) > 100:
                seen_content[cnt_h] = doc_id
            if ttl_h and date and pub:
                seen_near[(pub, date, ttl_h)] = doc_id

            # Ensure clean duplicate_status on canonical docs
            if "duplicate_status" not in doc or not doc["duplicate_status"].get("is_duplicate"):
                doc["duplicate_status"] = {
                    "is_duplicate":              False,
                    "duplicate_group_id":        None,
                    "canonical_document_for_group": True,
                }

    return documents, groups
