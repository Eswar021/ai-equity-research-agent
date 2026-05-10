"""
intelligence_layer/memory_qualification/thesis_memory_manager.py — Layer 4

Creates and updates investment thesis memories.
A thesis tracks the why/what/risk/invalidation for an investment idea.

Design doc: docs/system_design_docs/layer_4.md §12 thesis_memory_manager.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

# Event types that suggest a sector/theme opportunity thesis
_OPPORTUNITY_EVENT_TYPES = {
    "policy_change", "industrial_corridor", "real_estate_policy",
    "capex_announcement", "large_order_win", "private_company_funding",
}
# Event types that are risk factors (weakening signals)
_RISK_EVENT_TYPES = {
    "guidance_cut", "margin_pressure", "revenue_decline", "earnings_miss",
    "fraud_or_accounting_concern", "legal_issue", "regulatory_action",
    "credit_rating_change",
}


def process(candidate: dict, decision: dict,
            thesis_file: Path, entity_index: dict) -> dict | None:
    """
    Create a new thesis or update an existing one.

    Returns the thesis record written/updated, or None if not applicable.
    """
    decision_type = decision.get("decision", "")
    if decision_type not in ("store_as_thesis_update", "store_new") or \
       decision.get("memory_type") != "thesis_memory":
        return None

    obj      = candidate.get("_obj") or {}
    obj_type = candidate.get("source_object_type", "")
    evt_type = obj.get("event_type", "")

    # Try to find a related existing thesis
    existing = _find_related_thesis(candidate, thesis_file)

    if existing:
        return _update_thesis(existing, candidate, obj, evt_type, thesis_file)
    else:
        return _create_thesis(candidate, obj, obj_type, evt_type, thesis_file)


def _create_thesis(candidate: dict, obj: dict, obj_type: str,
                   evt_type: str, thesis_file: Path) -> dict:
    _CTR[0] += 1
    today   = datetime.now(_IST).strftime("%Y%m%d")
    tid     = f"THESIS_{today}_{_CTR[0]:04d}"
    now     = datetime.now(_IST).isoformat()

    thesis_type = "sector_theme_opportunity" if evt_type in _OPPORTUNITY_EVENT_TYPES else "risk_signal"
    core        = _build_core_thesis(obj, evt_type, candidate)

    record = {
        "thesis_id":    tid,
        "status":       "active",
        "thesis_type":  thesis_type,
        "title":        candidate.get("candidate_summary", "")[:200],
        "core_thesis":  core,

        "created_at":   now,
        "updated_at":   now,

        "time_horizon": candidate.get("initial_time_horizon", "unknown"),
        "linked_entities":  candidate.get("linked_entities") or [],
        "linked_themes":    candidate.get("linked_themes") or [],
        "candidate_targets": [],

        "supporting_evidence_refs":   candidate.get("source_refs") or [],
        "contradicting_evidence_refs": [],

        "open_questions":        _open_questions(evt_type),
        "invalidation_conditions": _invalidation_conditions(evt_type),

        "confidence": round(float(candidate.get("source_confidence", 0.55)), 3),
        "next_action": "send_to_opportunity_intelligence_and_proxy_mapping",

        "source_object_type": obj_type,
        "source_object_id":   candidate.get("source_object_id", ""),
        "research_run_id":    candidate.get("research_run_id", ""),
    }

    _append_thesis(record, thesis_file)
    return record


def _update_thesis(existing: dict, candidate: dict, obj: dict,
                   evt_type: str, thesis_file: Path) -> dict:
    now  = datetime.now(_IST).isoformat()
    is_risk = evt_type in _RISK_EVENT_TYPES

    if is_risk:
        existing.setdefault("contradicting_evidence_refs", []).extend(
            candidate.get("source_refs") or []
        )
        existing["confidence"] = round(max(0.1, existing.get("confidence", 0.5) - 0.05), 3)
        if existing["confidence"] < 0.3:
            existing["status"] = "weakened"
    else:
        existing.setdefault("supporting_evidence_refs", []).extend(
            candidate.get("source_refs") or []
        )
        existing["confidence"] = round(min(0.95, existing.get("confidence", 0.5) + 0.05), 3)

    for ent in (candidate.get("linked_entities") or []):
        if ent not in existing.get("linked_entities", []):
            existing.setdefault("linked_entities", []).append(ent)

    existing["updated_at"] = now
    _rewrite_thesis(existing, thesis_file)
    return existing


def _find_related_thesis(candidate: dict, thesis_file: Path) -> dict | None:
    if not thesis_file.exists():
        return None
    entities = {e.lower() for e in (candidate.get("linked_entities") or [])}
    themes   = {t.lower() for t in (candidate.get("linked_themes") or [])}

    for line in thesis_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") in ("archived", "invalidated"):
            continue
        rec_ents   = {e.lower() for e in (rec.get("linked_entities") or [])}
        rec_themes = {t.lower() for t in (rec.get("linked_themes") or [])}
        if (entities & rec_ents) or (themes & rec_themes):
            return rec
    return None


def _append_thesis(record: dict, thesis_file: Path) -> None:
    thesis_file.parent.mkdir(parents=True, exist_ok=True)
    with open(thesis_file, "a") as f:
        f.write(json.dumps(record) + "\n")


def _rewrite_thesis(updated: dict, thesis_file: Path) -> None:
    """Find and replace the thesis record in-file."""
    if not thesis_file.exists():
        _append_thesis(updated, thesis_file)
        return
    lines     = thesis_file.read_text().splitlines()
    new_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            new_lines.append(line)
            continue
        try:
            rec = json.loads(line)
            if rec.get("thesis_id") == updated.get("thesis_id"):
                new_lines.append(json.dumps(updated))
            else:
                new_lines.append(line)
        except json.JSONDecodeError:
            new_lines.append(line)
    thesis_file.write_text("\n".join(new_lines) + "\n")


# ── Content helpers ───────────────────────────────────────────────────────────

def _build_core_thesis(obj: dict, evt_type: str, candidate: dict) -> str:
    entities = ", ".join((candidate.get("linked_entities") or [])[:3])
    themes   = ", ".join((candidate.get("linked_themes") or [])[:2])
    summary  = candidate.get("candidate_summary", "")
    base     = f"{summary}"
    if entities:
        base += f" Entities involved: {entities}."
    if themes:
        base += f" Related themes: {themes}."
    return base


def _open_questions(evt_type: str) -> list[str]:
    base = [
        "Which listed Indian companies have direct exposure?",
        "Is order/revenue growth visible in company filings?",
        "Are valuations reasonable given the opportunity?",
    ]
    if evt_type in _OPPORTUNITY_EVENT_TYPES:
        base.append("Is the policy/event structural or a one-time occurrence?")
    return base


def _invalidation_conditions(evt_type: str) -> list[str]:
    return [
        "No visible order/revenue growth for 2-3 quarters",
        "Policy/event reversed or diluted",
        "Valuations become excessive without earnings support",
        "Multiple contradicting signals from high-reliability sources",
    ]
