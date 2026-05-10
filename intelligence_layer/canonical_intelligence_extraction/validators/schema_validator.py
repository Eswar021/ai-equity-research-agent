"""
intelligence_layer/canonical_intelligence_extraction/validators/schema_validator.py — Layer 3

Validates that every intelligence object has required fields and follows
allowed taxonomy values. Invalid objects are quarantined.

Checks (design doc §21):
  - Has an ID field
  - Has source_refs (non-empty)
  - Has confidence (0.0–1.0)
  - Has supporting_text when text-derived (checked by hallucination_precheck)
  - event_type, entity_type, claim_type, fact_type in allowed taxonomy
  - Does NOT have buy/sell recommendation fields

Design doc: docs/system_design_docs/layer_3.md §21 schema_validator.py
"""

from __future__ import annotations

# ── Allowed taxonomy values ────────────────────────────────────────────────────
_ALLOWED_ENTITY_TYPES = {
    "listed_company", "private_company", "business_group", "sector", "industry",
    "index", "commodity", "currency", "macro_indicator", "policy", "regulator",
    "government_body", "person", "product", "technology_theme", "regional_theme",
    "mutual_fund", "etf", "reit", "invit", "unknown",
}
_ALLOWED_FACT_TYPES = {
    "macro_policy_fact", "earnings_fact", "revenue_fact", "market_snapshot_fact",
    "institutional_flow_fact", "analyst_fact", "corporate_action_fact",
    "regulatory_fact", "management_statement_fact", "other_fact",
}
_ALLOWED_CLAIM_TYPES = {
    "opinion", "forecast", "rumor", "analyst_view",
    "management_guidance", "market_commentary", "promotional_claim",
}
_ALLOWED_EVENT_TYPES = {
    "earnings_beat", "earnings_miss", "guidance_raise", "guidance_cut",
    "margin_pressure", "revenue_growth", "revenue_decline",
    "large_order_win", "capex_announcement", "merger_acquisition",
    "divestment", "management_change", "regulatory_action", "legal_issue",
    "fraud_or_accounting_concern", "credit_rating_change",
    "dividend", "buyback", "split_bonus", "bulk_deal", "block_deal",
    "policy_change", "rate_decision", "inflation_data",
    "currency_move", "commodity_move", "sector_rotation",
    "analyst_upgrade", "analyst_downgrade", "ipo_news",
    "private_company_funding", "industrial_corridor", "real_estate_policy", "other",
}
_ALLOWED_THEME_TYPES = {
    "sector_theme", "macro_theme", "policy_theme", "technology_theme",
    "regional_theme", "commodity_theme", "cross_domain_theme", "other",
}
# Fields that must NOT appear on intelligence objects (anti-hallucination)
_FORBIDDEN_FIELDS = {"buy", "sell", "recommendation", "invest", "avoid"}


def _check(obj: dict, id_field: str, type_field: str,
           allowed_types: set, obj_type: str) -> list[str]:
    errors = []
    if not obj.get(id_field):
        errors.append(f"missing_{id_field}")
    if not obj.get("source_refs"):
        errors.append("missing_source_refs")
    conf = obj.get("confidence")
    if conf is None or not (0.0 <= float(conf) <= 1.0):
        errors.append(f"invalid_confidence={conf}")
    if type_field and obj.get(type_field) not in allowed_types:
        errors.append(f"{type_field}={obj.get(type_field)}_not_in_taxonomy")
    for ff in _FORBIDDEN_FIELDS:
        if ff in obj:
            errors.append(f"forbidden_field_{ff}")
    return errors


def validate_entities(entities: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in entities:
        errs = _check(obj, "entity_id", "entity_type", _ALLOWED_ENTITY_TYPES, "entity")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "entity"} for o, e in invalid if e],
    )

def validate_facts(facts: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in facts:
        errs = _check(obj, "fact_id", "fact_type", _ALLOWED_FACT_TYPES, "fact")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "fact"} for o, e in invalid if e],
    )

def validate_claims(claims: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in claims:
        errs = _check(obj, "claim_id", "claim_type", _ALLOWED_CLAIM_TYPES, "claim")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "claim"} for o, e in invalid if e],
    )

def validate_events(events: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in events:
        errs = _check(obj, "event_id", "event_type", _ALLOWED_EVENT_TYPES, "event")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "event"} for o, e in invalid if e],
    )

def validate_themes(themes: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in themes:
        errs = _check(obj, "theme_id", "theme_type", _ALLOWED_THEME_TYPES, "theme")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "theme"} for o, e in invalid if e],
    )

def validate_signals(signals: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obj in signals:
        errs = []
        if not obj.get("signal_id"):
            errs.append("missing_signal_id")
        if not obj.get("source_record_id") and not obj.get("source_refs"):
            errs.append("missing_source_ref")
        (invalid if errs else valid).append((obj, errs))
    return (
        [o for o, _ in valid],
        [{"object": o, "errors": e, "object_type": "signal"} for o, e in invalid if e],
    )


def validate_all(
    entities: list[dict],
    facts:    list[dict],
    claims:   list[dict],
    events:   list[dict],
    themes:   list[dict],
    signals:  list[dict],
) -> tuple[dict, list[dict]]:
    """
    Validate all objects. Returns (valid_sets, all_invalid).

    valid_sets: {"entities": [...], "facts": [...], ...}
    all_invalid: list of {"object": ..., "errors": [...], "object_type": ...}
    """
    ve, ie = validate_entities(entities)
    vf, if_ = validate_facts(facts)
    vc, ic  = validate_claims(claims)
    vev, iev = validate_events(events)
    vt, it  = validate_themes(themes)
    vs, is_ = validate_signals(signals)

    all_invalid = ie + if_ + ic + iev + it + is_
    return {
        "entities": ve, "facts": vf, "claims": vc,
        "events": vev, "themes": vt, "signals": vs,
    }, all_invalid
