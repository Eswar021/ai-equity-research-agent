"""
intelligence_layer/memory_qualification/memory_audit_logger.py — Layer 4

Appends one audit entry per memory decision to db/memory/memory_audit_index.jsonl.
This provides full traceability: why was something stored or ignored?

Design doc: docs/system_design_docs/layer_4.md §16 memory_audit_logger.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]


def log(candidate: dict, decision: dict, score_result: dict,
        memory_record: dict | None, audit_file: Path) -> dict:
    """
    Write one audit entry.

    Returns the audit entry dict.
    """
    _CTR[0] += 1
    today   = datetime.now(_IST).strftime("%Y%m%d")
    aid     = f"MEMAUDIT_{today}_{_CTR[0]:04d}"

    entry = {
        "audit_id":          aid,
        "candidate_id":      candidate.get("candidate_id", ""),
        "decision":          decision.get("decision", ""),
        "memory_id":         (memory_record or {}).get("memory_id") or (decision.get("matched_memory_ids") or [None])[0],
        "decision_reason":   decision.get("decision_reason", ""),
        "memory_score":      score_result.get("memory_score", 0),
        "score_breakdown":   score_result.get("score_breakdown") or {},
        "source_object_type": candidate.get("source_object_type", ""),
        "source_object_id":  candidate.get("source_object_id", ""),
        "source_refs":       candidate.get("source_refs") or [],
        "confidence":        decision.get("confidence", 0),
        "review_required":   decision.get("review_required", False),
        "timestamp":         datetime.now(_IST).isoformat(),
    }

    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def write_session_summary(summary: dict, audit_file: Path) -> None:
    """Append a session-level summary entry."""
    entry = {
        "audit_id":   f"MEMAUDIT_SESSION_{datetime.now(_IST).strftime('%Y%m%d_%H%M%S')}",
        "type":       "session_summary",
        "timestamp":  datetime.now(_IST).isoformat(),
        **summary,
    }
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
