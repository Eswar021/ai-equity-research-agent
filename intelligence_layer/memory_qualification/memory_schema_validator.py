"""
intelligence_layer/memory_qualification/memory_schema_validator.py — Layer 4

Validates memory records before writing to db/memory/.
Enforces hallucination-control rules: no source_refs → reject.

Design doc: docs/system_design_docs/layer_4.md §15 memory_schema_validator.py
"""

from __future__ import annotations

_VALID_MEMORY_TYPES = {
    "working_memory", "short_term_market_memory", "watch_memory",
    "long_term_investment_memory", "thesis_memory", "portfolio_memory",
}
_REQUIRED_FIELDS = {
    "memory_id", "memory_type", "status", "title", "summary",
    "created_at", "source_refs", "confidence",
}


def validate(record: dict) -> tuple[bool, list[str]]:
    """
    Validate a memory record.

    Returns (is_valid, error_list).
    """
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in record or record[field] is None:
            errors.append(f"missing_field:{field}")

    mem_type = record.get("memory_type", "")
    if mem_type not in _VALID_MEMORY_TYPES:
        errors.append(f"invalid_memory_type:{mem_type}")

    source_refs = record.get("source_refs") or []
    if not source_refs:
        errors.append("missing_source_refs")

    conf = record.get("confidence")
    if conf is not None:
        try:
            v = float(conf)
            if not (0.0 <= v <= 1.0):
                errors.append("confidence_out_of_range")
        except (TypeError, ValueError):
            errors.append("confidence_not_numeric")

    retention = record.get("retention") or {}
    if record.get("memory_type") not in ("thesis_memory", "portfolio_memory"):
        if not retention.get("retention_days") and record.get("memory_type") != "working_memory":
            errors.append("missing_retention_days")

    return len(errors) == 0, errors


def validate_batch(records: list[dict]) -> dict:
    """
    Validate a list of memory records.

    Returns:
        {valid_count, invalid_count, errors: [{memory_id, errors}]}
    """
    valid = 0
    invalid = 0
    error_list: list[dict] = []
    for rec in records:
        ok, errs = validate(rec)
        if ok:
            valid += 1
        else:
            invalid += 1
            error_list.append({"memory_id": rec.get("memory_id", "?"), "errors": errs})
    return {"valid_count": valid, "invalid_count": invalid, "errors": error_list}
