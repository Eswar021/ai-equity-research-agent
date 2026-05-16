"""
intelligence_layer/final_synthesis_layer/recommendation_policy_engine.py — Layer 10

Maps (score, confidence, risk_flags, data_gaps, disagreements) to a safe
final action label using deterministic policy rules.

Action labels (MVP set):
  research_candidate      — strong evidence, reasonable valuation, acceptable risk
  watchlist               — interesting but needs confirmation
  wait_for_confirmation   — idea real, evidence insufficient for action
  avoid_for_now           — risk/reward unattractive under current evidence
  too_speculative         — evidence too weak or indirect

Override rules (all downgrade by one level):
  - critical data gaps > 3
  - high-severity risk flags present AND score < 70
  - agent disagreements > 1
  - specialist confidence < 0.50
"""

from __future__ import annotations

_LABELS = [
    "research_candidate",
    "watchlist",
    "wait_for_confirmation",
    "avoid_for_now",
    "too_speculative",
]

# (score_min, confidence_min) → label
_SCORE_POLICY = [
    (70, 0.65, "research_candidate"),
    (55, 0.55, "watchlist"),
    (40, 0.45, "wait_for_confirmation"),
    (25, 0.0,  "avoid_for_now"),
    (0,  0.0,  "too_speculative"),
]

_ACTION_STRENGTH = {
    "research_candidate":    "high",
    "watchlist":             "medium",
    "wait_for_confirmation": "medium",
    "avoid_for_now":         "low",
    "too_speculative":       "low",
}


def apply_policy(ranked_item: dict, ctx: dict) -> dict:
    score      = ranked_item.get("final_opportunity_score", 0)
    confidence = ranked_item.get("overall_specialist_confidence",
                                  ranked_item.get("synthesis_confidence", 0.5))
    risk_flags = ctx.get("risk_flags", [])
    gaps       = ctx.get("critical_data_gaps", [])
    disagreements = ctx.get("disagreements", [])

    # ── Base label from score/confidence table ────────────────────────────────
    action_label = "too_speculative"
    for score_min, conf_min, label in _SCORE_POLICY:
        if score >= score_min and confidence >= conf_min:
            action_label = label
            break

    # ── Override rules (downgrade one level) ─────────────────────────────────
    override_reasons: list[str] = []

    high_risk_flags = [f for f in risk_flags if isinstance(f, dict) and f.get("severity") == "high"]
    if len(gaps) > 3:
        action_label, reason = _downgrade(action_label, f"{len(gaps)} critical data gaps present")
        if reason:
            override_reasons.append(reason)

    if high_risk_flags and score < 70:
        action_label, reason = _downgrade(action_label, f"{len(high_risk_flags)} high-severity risk flag(s)")
        if reason:
            override_reasons.append(reason)

    if len(disagreements) > 1:
        action_label, reason = _downgrade(action_label, f"{len(disagreements)} agent disagreements")
        if reason:
            override_reasons.append(reason)

    if confidence < 0.50:
        action_label, reason = _downgrade(action_label, f"low specialist confidence ({confidence:.2f})")
        if reason:
            override_reasons.append(reason)

    return {
        **ranked_item,
        "action_label":      action_label,
        "action_strength":   _ACTION_STRENGTH.get(action_label, "low"),
        "action_reasons":    _action_reasons(action_label, ranked_item, ctx),
        "policy_overrides":  override_reasons,
        "not_trade_execution": True,
    }


def apply_all(ranked_items: list[dict], ctx_by_tid: dict[str, dict]) -> list[dict]:
    return [apply_policy(item, ctx_by_tid.get(item["target_id"], {})) for item in ranked_items]


def _downgrade(label: str, reason: str) -> tuple[str, str]:
    idx = _LABELS.index(label) if label in _LABELS else len(_LABELS) - 1
    if idx < len(_LABELS) - 1:
        new_label = _LABELS[idx + 1]
        return new_label, f"Downgraded from {label} to {new_label}: {reason}"
    return label, ""


def _action_reasons(label: str, item: dict, ctx: dict) -> list[str]:
    reasons: list[str] = []
    dims = item.get("dimension_scores", {})
    f = dims.get("fundamental_score", 50)
    v = dims.get("valuation_score", 50)
    r = dims.get("risk_score", 50)
    t = dims.get("thesis_support_score", 50)

    if label == "research_candidate":
        reasons.append("Strong fundamental quality supports further research")
        if v >= 55:
            reasons.append("Valuation appears reasonably attractive")
        if t >= 55:
            reasons.append("Investment thesis has partial-to-strong support")
    elif label == "watchlist":
        reasons.append("Target shows potential but needs confirmation before action")
        if r > 55:
            reasons.append("Risk level warrants monitoring rather than immediate action")
    elif label == "wait_for_confirmation":
        reasons.append("Evidence is real but insufficient to support a high-conviction view")
        reasons.append("Additional data or management commentary needed")
    elif label == "avoid_for_now":
        if r > 65:
            reasons.append("Elevated risk profile outweighs current opportunity signals")
        if v < 35:
            reasons.append("Valuation does not offer sufficient margin of safety")
        if not reasons:
            reasons.append("Risk/reward unattractive under current evidence")
    else:
        reasons.append("Evidence is too weak or indirect to form a view")

    gaps = ctx.get("critical_data_gaps", [])
    if gaps:
        reasons.append(f"Note: {len(gaps)} critical data gap(s) limit confidence")

    return reasons
