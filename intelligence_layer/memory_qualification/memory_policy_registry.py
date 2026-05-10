"""
intelligence_layer/memory_qualification/memory_policy_registry.py — Layer 4

Rule-based memory qualification policies.
Each policy maps an object type + conditions → default memory type + retention.

Design doc: docs/system_design_docs/layer_4.md §3 memory_policy_registry.py
"""

from __future__ import annotations
from typing import Literal

# ── Policy definitions ────────────────────────────────────────────────────────

_POLICIES: list[dict] = [
    # ── Events: structural / regulatory → long-term ──────────────────────────
    {
        "policy_id": "POLICY_STRUCTURAL_EVENT",
        "applies_to": "event",
        "conditions": {
            "event_type": [
                "policy_change", "industrial_corridor", "real_estate_policy",
                "regulatory_action", "credit_rating_change", "merger_acquisition",
                "fraud_or_accounting_concern", "legal_issue",
            ],
            "severity": ["medium", "high"],
            "time_horizon": ["medium_term", "long_term"],
        },
        "default_memory_type": "long_term_investment_memory",
        "default_retention_days": 1095,
        "minimum_confidence": 0.60,
    },
    # ── Events: earnings / guidance → watch or thesis ─────────────────────────
    {
        "policy_id": "POLICY_EARNINGS_EVENT",
        "applies_to": "event",
        "conditions": {
            "event_type": [
                "earnings_beat", "earnings_miss", "guidance_raise", "guidance_cut",
                "margin_pressure", "revenue_growth", "revenue_decline",
                "analyst_upgrade", "analyst_downgrade",
            ],
            "severity": ["medium", "high"],
        },
        "default_memory_type": "watch_memory",
        "default_retention_days": 180,
        "minimum_confidence": 0.55,
    },
    # ── Events: corporate actions → short-term / watch ────────────────────────
    {
        "policy_id": "POLICY_CORPORATE_ACTION",
        "applies_to": "event",
        "conditions": {
            "event_type": [
                "dividend", "buyback", "split_bonus", "bulk_deal", "block_deal",
                "large_order_win", "capex_announcement", "management_change",
                "ipo_news", "private_company_funding",
            ],
        },
        "default_memory_type": "short_term_market_memory",
        "default_retention_days": 30,
        "minimum_confidence": 0.50,
    },
    # ── Events: macro / rate / currency → short-to-medium memory ─────────────
    {
        "policy_id": "POLICY_MACRO_EVENT",
        "applies_to": "event",
        "conditions": {
            "event_type": [
                "rate_decision", "inflation_data", "currency_move",
                "commodity_move", "sector_rotation",
            ],
        },
        "default_memory_type": "short_term_market_memory",
        "default_retention_days": 30,
        "minimum_confidence": 0.60,
    },
    # ── Themes: structural / cross-domain → long-term ─────────────────────────
    {
        "policy_id": "POLICY_STRUCTURAL_THEME",
        "applies_to": "theme",
        "conditions": {
            "theme_type": [
                "macro_theme", "policy_theme", "technology_theme", "cross_domain_theme",
            ],
            "time_horizon_hint": ["medium_term", "long_term"],
        },
        "default_memory_type": "long_term_investment_memory",
        "default_retention_days": 730,
        "minimum_confidence": 0.55,
    },
    # ── Themes: sector / regional → watch ─────────────────────────────────────
    {
        "policy_id": "POLICY_SECTOR_THEME",
        "applies_to": "theme",
        "conditions": {
            "theme_type": ["sector_theme", "regional_theme", "commodity_theme", "other"],
        },
        "default_memory_type": "watch_memory",
        "default_retention_days": 90,
        "minimum_confidence": 0.50,
    },
    # ── Facts: official / metric-bearing → watch or long-term ────────────────
    {
        "policy_id": "POLICY_OFFICIAL_FACT",
        "applies_to": "fact",
        "conditions": {
            "fact_type": [
                "macro_policy_fact", "regulatory_fact", "earnings_fact",
                "revenue_fact", "institutional_flow_fact",
            ],
        },
        "default_memory_type": "short_term_market_memory",
        "default_retention_days": 30,
        "minimum_confidence": 0.65,
    },
    # ── Claims: analyst / management guidance → watch ─────────────────────────
    {
        "policy_id": "POLICY_CLAIMS",
        "applies_to": "claim",
        "conditions": {
            "claim_type": ["analyst_view", "management_guidance", "forecast"],
            "requires_verification": True,
        },
        "default_memory_type": "watch_memory",
        "default_retention_days": 60,
        "minimum_confidence": 0.55,
    },
    # ── Market signals → short-term ───────────────────────────────────────────
    {
        "policy_id": "POLICY_MARKET_SIGNAL",
        "applies_to": "market_signal",
        "conditions": {},
        "default_memory_type": "short_term_market_memory",
        "default_retention_days": 7,
        "minimum_confidence": 0.70,
    },
]


def get_policies() -> list[dict]:
    """Return all configured memory policies."""
    return list(_POLICIES)


def match_policy(obj_type: str, obj: dict) -> dict | None:
    """
    Return the first matching policy for an object.
    Returns None if no policy matches (caller may use defaults).
    """
    for policy in _POLICIES:
        if policy["applies_to"] != obj_type:
            continue
        if _conditions_match(policy["conditions"], obj):
            return policy
    return None


def _conditions_match(conditions: dict, obj: dict) -> bool:
    for field, allowed in conditions.items():
        if field == "requires_verification":
            if bool(obj.get(field)) != bool(allowed):
                return False
            continue
        val = obj.get(field)
        if val is None:
            continue  # missing field does not disqualify
        if isinstance(allowed, list) and val not in allowed:
            return False
    return True
