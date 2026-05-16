"""
intelligence_layer/evidence_builder/agent_context_packet_builder.py — Layer 8

Builds 4 specialist agent context packets per target.

ADR-L8-009: 4 agent types built (fundamental, valuation, risk, thesis).
Skipped: market_agent, sector_agent (no sector targets), event_impact_agent
(needs L3 event cards), opportunity_proxy_agent (no private company targets).

Each packet contains only what the agent needs — no noise.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_AGENT_TYPES = ["fundamental_agent", "valuation_agent", "risk_agent", "thesis_agent"]

# Questions each agent is responsible for
_AGENT_QUESTIONS = {
    "fundamental_agent": [
        "What is the revenue and profit growth trajectory?",
        "Is the business quality improving or deteriorating (ROE, ROCE, margins)?",
        "How is the balance sheet? (debt levels, interest coverage)",
        "Is promoter confidence in the business strong?",
    ],
    "valuation_agent": [
        "Is the current valuation attractive relative to peers?",
        "What is the analyst consensus price target and upside?",
        "How does the PE/PB compare to sector median?",
        "Is the stock trading at a discount vs. historical norms?",
    ],
    "risk_agent": [
        "What are the key risks identified in filings and news?",
        "Is there any high debt, pledge risk, or promoter selling?",
        "What data is missing that could hide risks?",
        "Are there contradictions between management claims and numbers?",
    ],
    "thesis_agent": [
        "Does the collected evidence support or weaken the investment thesis?",
        "Under what conditions would the thesis be invalidated?",
        "What is the overall conviction level given available evidence?",
        "What additional information is needed to raise conviction?",
    ],
}

# Which evidence categories each agent uses
_AGENT_EVIDENCE_FILTER = {
    "fundamental_agent": {"categories": {"fundamentals", "earnings_revision"}, "types": {"numeric_feature"}},
    "valuation_agent":   {"categories": {"valuation", "analyst_consensus", "peer_comparison"}, "types": {"numeric_feature", "analyst_estimate", "peer_comparison"}},
    "risk_agent":        {"categories": {"risk_analysis", "exchange_filing", "missing_data_gap"}, "types": {"filing_fact", "missing_data_gap", "numeric_feature"}},
    "thesis_agent":      {"categories": None, "types": None},  # gets all cards
}

# Which feature groups each agent gets
_AGENT_FEATURE_GROUPS = {
    "fundamental_agent": {"FEAT_FUND", "FEAT_PRICE"},
    "valuation_agent":   {"FEAT_VAL", "FEAT_PEER", "FEAT_ANALYST", "FEAT_PRICE"},
    "risk_agent":        {"FEAT_FUND", "FEAT_PRICE"},
    "thesis_agent":      {"FEAT_FUND", "FEAT_VAL", "FEAT_PEER", "FEAT_ANALYST", "FEAT_PRICE"},
}

_AGENT_INSTRUCTIONS = {
    "fundamental_agent": [
        "Assess business quality using only the numeric features and evidence provided.",
        "Do not make a final buy/sell decision.",
        "Flag if any fundamental metrics are missing or unreliable.",
        "Assess if growth is improving, stable, or deteriorating.",
    ],
    "valuation_agent": [
        "Assess whether current valuation is attractive, fair, or expensive relative to peers.",
        "Do not make a final buy/sell decision.",
        "If analyst price targets or peer data are missing, lower confidence in valuation assessment.",
        "Reference specific numeric values from evidence in your assessment.",
    ],
    "risk_agent": [
        "Identify and assess key risks for this target.",
        "Pay special attention to missing data gaps — they hide unknown risks.",
        "Flag contradictions if any numeric fact conflicts with another.",
        "Do not dismiss risks because they seem unlikely — flag them with severity.",
    ],
    "thesis_agent": [
        "Synthesize all evidence to assess thesis strength.",
        "Explicitly identify supporting and weakening evidence.",
        "State which invalidating conditions are most likely given current data.",
        "Provide an overall conviction assessment: high/medium/low with rationale.",
        "Do not make a portfolio allocation recommendation.",
    ],
}


def build_all(
    scope:          dict,
    feature_groups: list[dict],
    evidence_cards: list[dict],
    thesis_card:    dict,
    evidence_gaps:  list[dict],
    evidence_pack:  dict,
    date_str:       str,
) -> list[dict]:
    """Build all 4 agent context packets for one target."""
    packets = []
    for agent_type in _AGENT_TYPES:
        pkt = _build_packet(
            agent_type, scope, feature_groups, evidence_cards,
            thesis_card, evidence_gaps, evidence_pack, date_str
        )
        packets.append(pkt)
    return packets


def _build_packet(
    agent_type:     str,
    scope:          dict,
    feature_groups: list[dict],
    evidence_cards: list[dict],
    thesis_card:    dict,
    evidence_gaps:  list[dict],
    evidence_pack:  dict,
    date_str:       str,
) -> dict:
    tid    = scope["target_id"]
    name   = scope["target_name"]
    ticker = scope["ticker"]

    # Filter evidence cards for this agent
    agent_cards = _filter_cards(evidence_cards, agent_type)
    agent_card_ids = [c["evidence_id"] for c in agent_cards]

    # Filter feature groups for this agent
    agent_fg_prefixes = _AGENT_FEATURE_GROUPS.get(agent_type, set())
    agent_fg_ids = [
        fg["feature_group_id"] for fg in feature_groups
        if any(fg["feature_group_id"].startswith(p) for p in agent_fg_prefixes)
    ]

    # Agent-specific questions (merge with target questions for thesis agent)
    agent_questions = list(_AGENT_QUESTIONS.get(agent_type, []))
    if agent_type == "thesis_agent":
        target_questions = scope.get("questions_to_answer", [])
        for q in target_questions[:5]:
            if q not in agent_questions:
                agent_questions.append(q)

    # Relevant gaps for this agent
    if agent_type == "risk_agent":
        gap_ids = [g["gap_id"] for g in evidence_gaps]
    elif agent_type == "thesis_agent":
        gap_ids = [g["gap_id"] for g in evidence_gaps if g.get("severity") in ("high", "medium")]
    else:
        gap_ids = []

    # Inline numeric features for the agent (flat dict for easy prompt injection)
    inline_features = _extract_inline_features(feature_groups, agent_type)

    return {
        "packet_id":             f"AGPACK_{date_str}_{tid}_{agent_type.upper()}",
        "target_id":             tid,
        "agent_type":            agent_type,
        "packet_version":        "v1",
        "target_summary": {
            "target_name":   name,
            "ticker":        ticker,
            "target_type":   scope.get("target_type", "listed_company"),
            "time_horizon":  scope.get("time_horizon", "unknown"),
            "priority_score": scope.get("priority_score"),
            "why_selected":  scope.get("why_selected", [])[:3],
        },
        "market_context":        scope.get("market_context", {}),
        "questions_for_agent":   agent_questions,
        "numeric_feature_group_ids": agent_fg_ids,
        "inline_features":       inline_features,
        "evidence_card_ids":     agent_card_ids,
        "evidence_cards":        agent_cards,  # inline for direct agent consumption
        "thesis_card_id":        thesis_card.get("thesis_card_id", ""),
        "thesis_card":           thesis_card if agent_type == "thesis_agent" else {
            "thesis_statement":         thesis_card.get("thesis_statement", ""),
            "current_thesis_confidence": thesis_card.get("current_thesis_confidence"),
            "invalidating_conditions":  thesis_card.get("invalidating_conditions", [])[:3],
        },
        "evidence_gap_ids":      gap_ids,
        "evidence_gaps":         [g for g in evidence_gaps if g["gap_id"] in gap_ids],
        "instructions":          _AGENT_INSTRUCTIONS.get(agent_type, []),
        "source_traceability_required": True,
        "created_at": datetime.now(_IST).isoformat(),
    }


def _filter_cards(cards: list[dict], agent_type: str) -> list[dict]:
    filt = _AGENT_EVIDENCE_FILTER.get(agent_type, {})
    categories = filt.get("categories")
    types      = filt.get("types")

    if categories is None and types is None:
        return cards

    result = []
    for card in cards:
        cat = card.get("evidence_category", "")
        typ = card.get("evidence_type", "")
        cat_match = categories is None or any(c in cat for c in categories)
        typ_match = types is None or typ in types
        if cat_match or typ_match:
            result.append(card)
    return result


def _extract_inline_features(feature_groups: list[dict], agent_type: str) -> dict:
    """Flatten relevant features into a single dict for quick prompt injection."""
    prefixes = _AGENT_FEATURE_GROUPS.get(agent_type, set())
    flat: dict[str, object] = {}
    for fg in feature_groups:
        if any(fg["feature_group_id"].startswith(p) for p in prefixes):
            group_name = fg.get("feature_group", fg["feature_group_id"])
            feats = fg.get("features", {})
            # Add group prefix to avoid key collision
            prefix = group_name.replace("_features", "")
            for k, v in feats.items():
                if v is not None:
                    flat[f"{prefix}.{k}"] = v
    return flat
