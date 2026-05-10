"""
intelligence_layer/memory_qualification/memory_updater.py — Layer 4

Updates existing memory records when recurring/update_to_existing decisions
are made. Increments occurrence count, appends new source refs, updates
last_seen_at and confidence.

Design doc: docs/system_design_docs/layer_4.md §11 memory_updater.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))

_MEMORY_FILES = [
    "short_term_market_memory.jsonl",
    "watch_memory.jsonl",
    "long_term_investment_memory.jsonl",
    "thesis_memory.jsonl",
    "portfolio_memory.jsonl",
]


def update(candidate: dict, decision: dict, db_memory_dir: Path) -> list[dict]:
    """
    Update existing memory records matched by decision.matched_memory_ids.

    Returns list of update records (what changed).
    """
    decision_type = decision.get("decision", "")
    if decision_type not in ("update_existing",):
        return []

    matched_ids = decision.get("matched_memory_ids") or []
    if not matched_ids:
        return []

    now          = datetime.now(_IST).isoformat()
    new_src_refs = candidate.get("source_refs") or []
    new_conf     = float(candidate.get("source_confidence", 0.5))
    updates: list[dict] = []

    for fname in _MEMORY_FILES:
        fpath = db_memory_dir / fname
        if not fpath.exists():
            continue

        lines   = fpath.read_text().splitlines()
        changed = False
        new_lines: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                new_lines.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue

            if rec.get("memory_id") in matched_ids:
                update_log = _apply_update(rec, now, new_src_refs, new_conf, candidate)
                new_lines.append(json.dumps(rec))
                updates.append(update_log)
                changed = True
            else:
                new_lines.append(line)

        if changed:
            fpath.write_text("\n".join(new_lines) + "\n")

    return updates


def _apply_update(rec: dict, now: str, new_src_refs: list,
                  new_conf: float, candidate: dict) -> dict:
    """Mutate rec in-place. Return a change log dict."""
    old_conf  = float(rec.get("confidence", 0.5))
    old_count = int((rec.get("recurrence") or {}).get("occurrence_count", 1))

    rec["last_seen_at"] = now
    rec["updated_at"]   = now

    recurrence = rec.setdefault("recurrence", {})
    recurrence["occurrence_count"] = old_count + 1

    # Merge new source refs
    existing_refs = rec.get("source_refs") or []
    existing_ids  = {r.get("document_id") or r.get("record_id") for r in existing_refs}
    for sr in new_src_refs:
        sr_id = sr.get("document_id") or sr.get("record_id")
        if sr_id and sr_id not in existing_ids:
            existing_refs.append(sr)
            existing_ids.add(sr_id)
    rec["source_refs"] = existing_refs
    recurrence["source_diversity_count"] = len(
        {r.get("source_id") or r.get("document_id") or "" for r in existing_refs}
    )

    # Confidence: small positive nudge for recurring evidence (max 0.95)
    delta = min((new_conf - old_conf) * 0.3, 0.05)
    rec["confidence"] = round(min(old_conf + max(delta, 0), 0.95), 3)

    # Append linked objects from candidate if not already present
    for link_key in ("linked_events", "linked_themes", "linked_facts", "linked_claims"):
        existing = set(rec.get(link_key) or [])
        for item in (candidate.get(link_key) or []):
            if item and item not in existing:
                rec.setdefault(link_key, []).append(item)
                existing.add(item)

    return {
        "memory_id":        rec["memory_id"],
        "update_type":      "recurrence_update",
        "updated_fields": {
            "last_seen_at":       now,
            "occurrence_count":   recurrence["occurrence_count"],
            "new_source_refs":    len(new_src_refs),
        },
        "confidence_change": round(rec["confidence"] - old_conf, 3),
    }
