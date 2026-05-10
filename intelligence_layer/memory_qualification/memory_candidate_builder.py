"""
intelligence_layer/memory_qualification/memory_candidate_builder.py — Layer 4

Converts Layer 3 intelligence objects into memory candidates.
Not every extracted object becomes memory — this filters by minimum signal quality.

Design doc: docs/system_design_docs/layer_4.md §4 memory_candidate_builder.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST  = timezone(timedelta(hours=5, minutes=30))
_CTR  = [0]

_SEVERITY_FILTER  = {"medium", "high"}
_MIN_CONF_EVENT   = 0.45
_MIN_CONF_THEME   = 0.45
_MIN_CONF_FACT    = 0.55
_MIN_CONF_CLAIM   = 0.50
_MIN_CONF_SIGNAL  = 0.65


def _cid() -> str:
    _CTR[0] += 1
    today = datetime.now(_IST).strftime("%Y%m%d")
    return f"MEMCAND_{today}_{_CTR[0]:04d}"


def build_candidates(intelligence: dict, run_id: str = "") -> list[dict]:
    """
    Convert Layer 3 objects to memory candidates.

    Args:
        intelligence: dict returned by intelligence_input_loader.load()
        run_id:       research_run_id for traceability

    Returns:
        list of memory candidate dicts
    """
    candidates: list[dict] = []

    for evt in intelligence.get("events") or []:
        if _should_candidate_event(evt):
            candidates.append(_make_candidate(evt, "event", run_id))

    for theme in intelligence.get("themes") or []:
        if _should_candidate_theme(theme):
            candidates.append(_make_candidate(theme, "theme", run_id))

    for fact in intelligence.get("facts") or []:
        if _should_candidate_fact(fact):
            candidates.append(_make_candidate(fact, "fact", run_id))

    for claim in intelligence.get("claims") or []:
        if _should_candidate_claim(claim):
            candidates.append(_make_candidate(claim, "claim", run_id))

    for sig in intelligence.get("market_signals") or []:
        if _should_candidate_signal(sig):
            candidates.append(_make_candidate(sig, "market_signal", run_id))

    return candidates


# ── Per-type inclusion filters ───────────────────────────────────────────────

def _should_candidate_event(evt: dict) -> bool:
    severity = evt.get("severity", "low")
    conf     = float(evt.get("confidence", 0))
    if conf < _MIN_CONF_EVENT:
        return False
    if severity in _SEVERITY_FILTER:
        return True
    # low severity only if source_reliability is high
    return (evt.get("source_reliability") or "") == "high"


def _should_candidate_theme(theme: dict) -> bool:
    return float(theme.get("confidence", 0)) >= _MIN_CONF_THEME


def _should_candidate_fact(fact: dict) -> bool:
    if float(fact.get("confidence", 0)) < _MIN_CONF_FACT:
        return False
    # must have a metric or be a known high-value type
    high_value_types = {
        "macro_policy_fact", "earnings_fact", "revenue_fact",
        "institutional_flow_fact", "regulatory_fact", "analyst_fact",
    }
    return (fact.get("metric_value") is not None or
            fact.get("fact_type") in high_value_types)


def _should_candidate_claim(claim: dict) -> bool:
    if float(claim.get("confidence", 0)) < _MIN_CONF_CLAIM:
        return False
    # only watch-worthy claim types
    worth_watching = {"analyst_view", "management_guidance", "forecast", "rumor"}
    return (bool(claim.get("requires_verification")) or
            claim.get("claim_type") in worth_watching)


def _should_candidate_signal(sig: dict) -> bool:
    return float(sig.get("confidence", 0)) >= _MIN_CONF_SIGNAL


# ── Candidate factory ────────────────────────────────────────────────────────

def _make_candidate(obj: dict, obj_type: str, run_id: str) -> dict:
    obj_id    = obj.get("entity_id") or obj.get("fact_id") or obj.get("claim_id") \
                or obj.get("event_id") or obj.get("theme_id") or obj.get("signal_id") \
                or obj.get("id") or ""
    summary   = _summarize(obj, obj_type)
    # entities field may be list[str] or list[dict] depending on extractor
    entities  = _extract_entity_names(obj.get("entities") or [])
    if obj.get("entity_name"):
        entities.append(obj["entity_name"])
    themes    = obj.get("linked_themes") or obj.get("themes") or []
    if obj_type == "theme":
        themes = [obj.get("theme_name", "")]

    return {
        "candidate_id":        _cid(),
        "research_run_id":     run_id,
        "source_object_type":  obj_type,
        "source_object_id":    obj_id,
        "candidate_summary":   summary,
        "linked_entities":     [e for e in entities if e],
        "linked_themes":       [t for t in themes if t],
        "linked_facts":        [],
        "linked_claims":       [],
        "linked_events":       [obj_id] if obj_type == "event" else [],
        "source_refs":         obj.get("source_refs") or [],
        "initial_time_horizon": _time_horizon(obj, obj_type),
        "source_confidence":   float(obj.get("confidence", 0.5)),
        "source_reliability":  obj.get("source_reliability", "medium"),
        # pass-through fields for scorer
        "_obj":                obj,
    }


def _summarize(obj: dict, obj_type: str) -> str:
    if obj_type == "event":
        return obj.get("event_title") or obj.get("event_summary") or "Event"
    if obj_type == "theme":
        return obj.get("theme_name") or obj.get("description") or "Theme"
    if obj_type == "fact":
        return obj.get("fact_text") or "Fact"
    if obj_type == "claim":
        return obj.get("claim_text") or "Claim"
    if obj_type == "market_signal":
        return obj.get("signal_name") or obj.get("metric_name") or "Market signal"
    return "Unknown"


def _extract_entity_names(raw_entities: list) -> list[str]:
    """Normalize entities to a list of strings, handling both str and dict formats."""
    names: list[str] = []
    for e in raw_entities:
        if isinstance(e, str):
            names.append(e)
        elif isinstance(e, dict):
            name = e.get("entity_name") or e.get("name") or ""
            if name:
                names.append(name)
    return names


def _time_horizon(obj: dict, obj_type: str) -> str:
    for key in ("time_horizon", "time_horizon_hint", "time_horizon_hint"):
        v = obj.get(key)
        if v and v != "unknown":
            return v
    if obj_type == "market_signal":
        return "short_term"
    return "unknown"
