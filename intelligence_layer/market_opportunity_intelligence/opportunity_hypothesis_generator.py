"""
intelligence_layer/market_opportunity_intelligence/opportunity_hypothesis_generator.py — Layer 5

LLM-driven opportunity hypothesis generator.
For each qualifying signal group, generates 1-3 investment opportunity hypotheses.

One LLM call per qualifying signal group via Pydantic with_structured_output.

Design doc: docs/system_design_docs/layer_5.md §7 opportunity_hypothesis_generator.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional

from pydantic import BaseModel

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_SYSTEM_PROMPT = """\
You are a market and opportunity intelligence model for Indian equity markets.

You receive a signal group: events, themes, claims, and entity information from market news/filings.
Generate 1-3 investment opportunity hypotheses from this signal group.
Each hypothesis suggests a POSSIBLE opportunity for deeper research — not a buy/sell recommendation.

Rules:
- Do NOT recommend buying or selling.
- Every hypothesis must reference evidence in the signal group.
- hypothesis_strength = "high": multiple sources AND structural relevance both confirmed.
- hypothesis_strength = "low": speculative or single weak source.
- time_horizon = "structural": only for policy changes, industrial corridors, multi-year capex cycles.
- likely_beneficiaries_or_targets: name real Indian NSE-listed companies where possible (max 5).
- If there is NO clear investment angle, return an empty hypotheses list.
- Return JSON matching the schema exactly.
"""


class BeneficiaryTarget(BaseModel):
    entity_name: str
    ticker: Optional[str] = None
    target_type: str   # listed_company | sector_theme | fund_etf | commodity | real_estate_theme
    mapping_status: str  # candidate_needs_deep_dive | sector_needs_deep_dive | proxy_mapping_needed


class OpportunityHypothesis(BaseModel):
    opportunity_title: str
    opportunity_type: str   # listed_stock | sector_theme | macro_theme | fund_etf | cross_domain | ...
    hypothesis: str         # 2-3 sentences
    affected_markets: list[str]
    potential_target_types: list[str]
    likely_beneficiaries_or_targets: list[BeneficiaryTarget]
    time_horizon: str       # short_term | medium_term | long_term | structural
    hypothesis_strength: str  # low | medium | high
    requires_deep_dive: bool
    required_deep_dive_questions: list[str]
    invalidating_conditions: list[str]
    data_gaps: list[str]


class HypothesisBundle(BaseModel):
    hypotheses: list[OpportunityHypothesis]


_MAX_GROUPS = 50   # cap LLM calls per run; sorted by priority score


def generate_all(signal_groups: list[dict], sector_theme_views: list[dict],
                 event_impact_views: list[dict], market_view: dict, llm) -> list[dict]:
    """
    Generate opportunity hypotheses for the top qualifying signal groups.
    Groups are ranked by priority score; only the top _MAX_GROUPS are sent to the LLM.
    Returns enriched hypothesis dicts with IDs, origin refs, timestamps.
    """
    theme_view_by_grp: dict[str, dict] = {
        v["signal_group_id"]: v for v in sector_theme_views
    }
    impact_by_event: dict[str, dict] = {
        v["event_id"]: v for v in event_impact_views
    }

    # Filter and rank signal groups before LLM calls
    qualified = _rank_and_filter(signal_groups, theme_view_by_grp)[:_MAX_GROUPS]

    results: list[dict] = []
    total = len(qualified)
    for i, grp in enumerate(qualified, 1):
        print(f"       [{i}/{total}] {grp.get('theme', '')[:55]}", flush=True)
        grp_id     = grp.get("signal_group_id", "")
        theme_view = theme_view_by_grp.get(grp_id, {})

        context = _build_context(grp, theme_view, impact_by_event, market_view)
        bundle  = _call_llm(context, llm)
        if not bundle or not bundle.hypotheses:
            continue

        for hyp in bundle.hypotheses:
            results.append(_enrich(hyp, grp, theme_view))

    return results


def _priority_score(grp: dict, tv: dict) -> int:
    """Score a signal group 0-100 for hypothesis generation priority."""
    ir_pts  = {"high": 30, "medium": 15, "low": 0}
    ss_pts  = {"high": 25, "medium": 12, "low": 0}
    sr_pts  = {"high": 15, "medium": 7,  "low": 0}
    score   = ir_pts.get(tv.get("investment_relevance", "low"), 0)
    score  += ss_pts.get(tv.get("current_signal_strength", "low"), 0)
    score  += sr_pts.get(tv.get("structural_relevance", "low"), 0)
    score  += min(len(grp.get("event_ids") or []) * 3, 15)   # up to 15 for events
    score  += min(grp.get("source_diversity_count", 0) * 2, 10)
    score  += 5 if grp.get("memory_refs") else 0
    return score


def _rank_and_filter(signal_groups: list[dict],
                     theme_view_by_grp: dict[str, dict]) -> list[dict]:
    """Return groups sorted by priority, skipping those with no investment angle."""
    ranked: list[tuple[int, dict]] = []
    for grp in signal_groups:
        tv = theme_view_by_grp.get(grp.get("signal_group_id", ""), {})
        ir = tv.get("investment_relevance", "low")
        # Skip low investment relevance with no memory or events
        if ir == "low" and not grp.get("memory_refs") and not grp.get("event_ids"):
            continue
        # Must have some content
        if not grp.get("event_ids") and not grp.get("fact_ids") and not grp.get("claim_ids"):
            continue
        ranked.append((_priority_score(grp, tv), grp))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [g for _, g in ranked]


def _build_context(grp: dict, theme_view: dict,
                   impact_by_event: dict, market_view: dict) -> str:
    lines: list[str] = []

    lines.append(f"THEME: {grp.get('theme', '')} (type={grp.get('theme_type', 'unknown')})")
    lines.append(f"ENTITIES: {', '.join((grp.get('entities') or [])[:8]) or 'none'}")
    lines.append(
        f"SOURCE DIVERSITY: {grp.get('source_diversity_count', 0)} sources | "
        f"RECURRENCE: {grp.get('recurrence_level', 'new')} | "
        f"MEMORY: {'yes' if grp.get('memory_refs') else 'no'} | "
        f"MENTIONS: {grp.get('mention_count', 1)}"
    )

    if theme_view:
        lines.append(
            f"SIGNAL STRENGTH: {theme_view.get('current_signal_strength', '?')} | "
            f"STRUCTURAL RELEVANCE: {theme_view.get('structural_relevance', '?')} | "
            f"INVESTMENT RELEVANCE: {theme_view.get('investment_relevance', '?')}"
        )
        opp_types = theme_view.get("possible_opportunity_types") or []
        lines.append(f"POSSIBLE OPPORTUNITY TYPES: {opp_types}")

    events_detail = (grp.get("events_detail") or [])[:5]
    if events_detail:
        lines.append("EVENTS:")
        for evt in events_detail:
            eid      = evt.get("event_id", "")
            evt_type = evt.get("event_type", "?")
            title    = evt.get("event_title", "") or evt.get("headline", "")
            sev      = evt.get("severity", "?")
            impact   = impact_by_event.get(eid, {})
            direction = impact.get("impact_direction", "?")
            lines.append(f"  [{evt_type}|sev={sev}|{direction}] {title[:100]}")

    regime  = market_view.get("regime", "unknown")
    posture = market_view.get("recommended_posture", "unknown")
    favored = (market_view.get("sectors") or {}).get("favored") or []
    lines.append(f"MARKET REGIME: {regime} | POSTURE: {posture} | FAVORED: {favored[:5]}")

    return "\n".join(lines)[:2200]


def _call_llm(context: str, llm) -> HypothesisBundle | None:
    structured = llm.with_structured_output(HypothesisBundle)
    prompt = f"{_SYSTEM_PROMPT}\n\nSIGNAL GROUP CONTEXT:\n{context}"
    try:
        return structured.invoke(prompt)
    except Exception as e:
        # Surface the error type so the caller can distinguish quota vs real failures
        print(f"         LLM error: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return None


def _enrich(hyp: OpportunityHypothesis, grp: dict, theme_view: dict) -> dict:
    _CTR[0] += 1
    today  = datetime.now(_IST).strftime("%Y%m%d")
    opp_id = f"OPP_{today}_{_CTR[0]:04d}"

    origin = {
        "source_type":      "signal_group",
        "signal_group_id":  grp.get("signal_group_id", ""),
        "event_refs":       (grp.get("event_ids") or [])[:5],
        "theme_refs":       [grp["theme_id"]] if grp.get("theme_id") else [],
        "memory_refs":      (grp.get("memory_refs") or [])[:3],
        "claim_refs":       (grp.get("claim_ids") or [])[:3],
        "fact_refs":        (grp.get("fact_ids") or [])[:3],
    }

    base_conf = grp.get("confidence", 0.5)
    if   hyp.hypothesis_strength == "high":   conf = min(base_conf + 0.10, 0.90)
    elif hyp.hypothesis_strength == "medium": conf = min(base_conf + 0.05, 0.80)
    else:                                     conf = min(base_conf,         0.65)

    return {
        "opportunity_id":                   opp_id,
        "opportunity_title":                hyp.opportunity_title,
        "opportunity_type":                 hyp.opportunity_type,
        "hypothesis":                       hyp.hypothesis,
        "origin":                           origin,
        "affected_markets":                 hyp.affected_markets,
        "potential_target_types":           hyp.potential_target_types,
        "likely_beneficiaries_or_targets":  [t.model_dump() for t in hyp.likely_beneficiaries_or_targets],
        "time_horizon":                     hyp.time_horizon,
        "hypothesis_strength":              hyp.hypothesis_strength,
        "requires_deep_dive":               hyp.requires_deep_dive,
        "required_deep_dive_questions":     hyp.required_deep_dive_questions,
        "invalidating_conditions":          hyp.invalidating_conditions,
        "supporting_refs":                  (grp.get("source_refs") or [])[:5],
        "data_gaps":                        hyp.data_gaps,
        "confidence":                       round(conf, 3),
    }
