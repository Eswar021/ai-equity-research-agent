"""
intelligence_layer/memory_qualification/memory_writer.py — Layer 4

Writes new validated memory records to db/memory/ JSONL stores.
Updates entity_memory_index.json and theme_memory_index.json.

Design doc: docs/system_design_docs/layer_4.md §10 memory_writer.py
"""

from __future__ import annotations
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_MEMORY_TYPE_TO_FILE = {
    "working_memory":             "working_memory/current_run_memory.json",
    "short_term_market_memory":   "short_term_market_memory.jsonl",
    "watch_memory":               "watch_memory.jsonl",
    "long_term_investment_memory": "long_term_investment_memory.jsonl",
    "thesis_memory":              "thesis_memory.jsonl",
    "portfolio_memory":           "portfolio_memory.jsonl",
}


def write(candidate: dict, decision: dict, db_memory_dir: Path) -> dict | None:
    """
    Build and write a new memory record.

    Returns the written memory record, or None if rejected by decision type.
    """
    decision_type = decision.get("decision", "")
    if decision_type in ("ignore_noise", "update_existing", "quarantine",
                         "store_as_thesis_update"):
        return None  # not a new record write

    mem_type   = decision.get("memory_type", "short_term_market_memory")
    ret_days   = decision.get("retention_days", 30)
    decay      = decision.get("decay_policy", "medium_decay")
    obj        = candidate.get("_obj") or {}
    confidence = float(candidate.get("source_confidence", 0.5))

    record = _build_record(candidate, obj, mem_type, ret_days, decay, confidence)
    _persist(record, mem_type, db_memory_dir)
    _update_indexes(record, db_memory_dir)
    return record


def _build_record(candidate: dict, obj: dict, mem_type: str,
                  ret_days: int, decay: str, confidence: float) -> dict:
    _CTR[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    mid   = f"MEM_{today}_{_CTR[0]:04d}"
    now   = datetime.now(_IST).isoformat()

    expires_at = ""
    if ret_days > 0:
        exp = (datetime.now(_IST) + timedelta(days=ret_days)).date().isoformat()
        expires_at = exp

    return {
        "memory_id":         mid,
        "memory_type":       mem_type,
        "status":            "active",

        "title":             candidate.get("candidate_summary", "")[:200],
        "summary":           candidate.get("candidate_summary", ""),
        "memory_scope":      _scope(obj, candidate),
        "time_horizon":      candidate.get("initial_time_horizon", "unknown"),

        "linked_entities":   candidate.get("linked_entities") or [],
        "linked_themes":     candidate.get("linked_themes") or [],
        "linked_events":     candidate.get("linked_events") or [],
        "linked_facts":      candidate.get("linked_facts") or [],
        "linked_claims":     candidate.get("linked_claims") or [],

        "source_refs":       candidate.get("source_refs") or [],
        "why_stored":        _why(candidate, obj),
        "future_use_cases":  _future_use(mem_type),

        "recurrence": {
            "occurrence_count":    1,
            "source_diversity_count": len({
                (r.get("source_id") or r.get("document_id") or "")
                for r in (candidate.get("source_refs") or [])
            }),
        },

        "retention": {
            "retention_days": ret_days,
            "expires_at":     expires_at,
            "decay_policy":   decay,
        },

        "created_at":  now,
        "updated_at":  now,
        "last_seen_at": now,
        "confidence":  round(confidence, 3),

        # traceability
        "source_object_type": candidate.get("source_object_type", ""),
        "source_object_id":   candidate.get("source_object_id", ""),
        "research_run_id":    candidate.get("research_run_id", ""),
    }


def _persist(record: dict, mem_type: str, db_memory_dir: Path) -> None:
    rel = _MEMORY_TYPE_TO_FILE.get(mem_type, "short_term_market_memory.jsonl")
    path = db_memory_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    if rel.endswith(".jsonl"):
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    else:
        # working_memory is a JSON list
        existing: list[dict] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                existing = []
        existing.append(record)
        path.write_text(json.dumps(existing, indent=2))


def _update_indexes(record: dict, db_memory_dir: Path) -> None:
    mid = record["memory_id"]

    ei_path = db_memory_dir / "entity_memory_index.json"
    ti_path = db_memory_dir / "theme_memory_index.json"

    ei = json.loads(ei_path.read_text()) if ei_path.exists() else {}
    ti = json.loads(ti_path.read_text()) if ti_path.exists() else {}

    for ent in (record.get("linked_entities") or []):
        key = ent.lower()
        ei.setdefault(key, [])
        if mid not in ei[key]:
            ei[key].append(mid)

    for th in (record.get("linked_themes") or []):
        key = th.lower()
        ti.setdefault(key, [])
        if mid not in ti[key]:
            ti[key].append(mid)

    ei_path.write_text(json.dumps(ei, indent=2))
    ti_path.write_text(json.dumps(ti, indent=2))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scope(obj: dict, candidate: dict) -> list[str]:
    scope: list[str] = []
    obj_type = candidate.get("source_object_type", "")
    if obj_type == "event":
        scope.extend(obj.get("impact_scope") or [])
    if candidate.get("linked_entities"):
        if "company" not in scope:
            scope.append("company")
    if candidate.get("linked_themes"):
        if "sector" not in scope:
            scope.append("sector")
    return list(dict.fromkeys(scope)) or ["unknown"]


def _why(candidate: dict, obj: dict) -> str:
    obj_type = candidate.get("source_object_type", "")
    if obj_type == "event":
        return f"{obj.get('event_type', 'event')} with {obj.get('severity','?')} severity"
    if obj_type == "theme":
        return f"Theme '{obj.get('theme_name','?')}' — {obj.get('theme_type','?')}"
    if obj_type == "fact":
        return f"Fact: {obj.get('fact_type','?')} with metric"
    if obj_type == "claim":
        return f"Claim requiring verification: {obj.get('claim_type','?')}"
    return f"{obj_type} memory"


def _future_use(mem_type: str) -> list[str]:
    return {
        "long_term_investment_memory": ["sector opportunity analysis", "thesis creation", "long-term tracking"],
        "watch_memory":                ["company deep dive", "thesis monitoring", "risk tracking"],
        "short_term_market_memory":    ["market regime context", "short-term signal"],
        "thesis_memory":               ["investment thesis tracking", "conviction building"],
        "working_memory":              ["current run context"],
        "portfolio_memory":            ["portfolio review", "hold/exit decision"],
    }.get(mem_type, ["future analysis"])
