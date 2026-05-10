"""
intelligence_layer/canonical_intelligence_extraction/validators/source_ref_validator.py — Layer 3

Verifies that every extracted intelligence object traces back to a real Layer 2
source document or structured record. This is the primary hallucination control
gate: if we cannot trace the object to a source, it is invalid.

"This is essential for hallucination control." — design doc §22

Design doc: docs/system_design_docs/layer_3.md §22 source_ref_validator.py
"""

from __future__ import annotations


def validate(
    objects:        list[dict],
    document_ids:   set[str],
    record_ids:     set[str],
    source_ledger:  list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Validate that every object's source_refs point to real Layer 2 artifacts.

    Args:
        objects:       list of intelligence objects (any type)
        document_ids:  set of canonical document_ids from Layer 2
        record_ids:    set of canonical record_ids from Layer 2
        source_ledger: list of source ledger entries (for source_id validation)

    Returns:
        (valid_objects, invalid_objects)
        invalid_objects carry an 'validation_error' field.
    """
    valid_source_ids = {entry.get("canonical_source_id", "") for entry in source_ledger}

    valid:   list[dict] = []
    invalid: list[dict] = []

    for obj in objects:
        refs     = obj.get("source_refs", [])
        if not refs:
            obj["validation_error"] = "no_source_refs"
            invalid.append(obj)
            continue

        all_valid = True
        errors    = []

        for ref in refs:
            doc_id    = ref.get("document_id", "")
            rec_id    = ref.get("record_id", "")
            source_id = ref.get("source_id", "")

            # Must have document_id OR record_id
            if doc_id and doc_id not in document_ids:
                errors.append(f"document_id={doc_id}_not_found_in_layer2")
                all_valid = False

            if rec_id and rec_id not in record_ids:
                errors.append(f"record_id={rec_id}_not_found_in_layer2")
                all_valid = False

            if not doc_id and not rec_id:
                errors.append("ref_has_neither_document_id_nor_record_id")
                all_valid = False

        if all_valid:
            valid.append(obj)
        else:
            obj["validation_error"] = "; ".join(errors)
            invalid.append(obj)

    return valid, invalid


def build_id_sets(documents: list[dict], records: list[dict]) -> tuple[set, set]:
    """Build sets of known document_ids and record_ids from Layer 2 outputs."""
    doc_ids = {d.get("document_id", "") for d in documents if d.get("document_id")}
    rec_ids = {r.get("record_id",   "") for r in records   if r.get("record_id")}
    return doc_ids, rec_ids
