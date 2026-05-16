"""
intelligence_layer/final_synthesis_layer/risk_confidence_calibrator.py — Layer 10

Post-hoc confidence adjustment for final target cards.
Applies penalies for: missing data, high-severity risks, disagreements,
weak evidence coverage. Upgrades for: strong multi-agent alignment.
"""

from __future__ import annotations


def calibrate_all(policy_results: list[dict], ctx_by_tid: dict[str, dict]) -> list[dict]:
    return [_calibrate_one(item, ctx_by_tid.get(item["target_id"], {})) for item in policy_results]


def _calibrate_one(item: dict, ctx: dict) -> dict:
    initial_conf = item.get("overall_specialist_confidence",
                             item.get("synthesis_confidence", 0.5))

    adjustments: list[tuple[float, str]] = []

    # ── Penalties ─────────────────────────────────────────────────────────────
    gaps = ctx.get("critical_data_gaps", [])
    if len(gaps) >= 5:
        adjustments.append((-0.10, "5+ critical data gaps"))
    elif len(gaps) >= 3:
        adjustments.append((-0.06, "3-4 critical data gaps"))
    elif len(gaps) >= 1:
        adjustments.append((-0.03, "1-2 critical data gaps"))

    risk_flags = ctx.get("risk_flags", [])
    high_rf = [f for f in risk_flags if isinstance(f, dict) and f.get("severity") == "high"]
    if len(high_rf) >= 3:
        adjustments.append((-0.08, f"{len(high_rf)} high-severity risk flags"))
    elif len(high_rf) >= 1:
        adjustments.append((-0.04, f"{len(high_rf)} high-severity risk flag(s)"))

    disagreements = ctx.get("disagreements", [])
    severe_disag = [d for d in disagreements if isinstance(d, dict) and d.get("severity") in ("high", "critical")]
    if severe_disag:
        adjustments.append((-0.06, f"{len(severe_disag)} severe agent disagreement(s)"))
    elif disagreements:
        adjustments.append((-0.03, f"{len(disagreements)} agent disagreement(s)"))

    dims = item.get("dimension_scores", {})
    t_score = dims.get("thesis_support_score", 50)
    if t_score < 35:
        adjustments.append((-0.05, "weak thesis support score"))

    # ── Upgrades ─────────────────────────────────────────────────────────────
    f_score = dims.get("fundamental_score", 50)
    v_score = dims.get("valuation_score", 50)
    if f_score >= 70 and v_score >= 55 and not high_rf:
        adjustments.append((+0.05, "strong fundamentals + acceptable valuation + no high-risk flags"))

    top_evidence = ctx.get("top_evidence_cards", [])
    strong_ev = [e for e in top_evidence if isinstance(e, dict) and e.get("strength_label") == "strong"]
    if len(strong_ev) >= 3:
        adjustments.append((+0.03, f"{len(strong_ev)} strong evidence cards"))

    # ── Apply ─────────────────────────────────────────────────────────────────
    total_adj = sum(a for a, _ in adjustments)
    final_conf = max(0.10, min(0.95, initial_conf + total_adj))

    label = _conf_label(final_conf)

    return {
        **item,
        "initial_confidence":    round(initial_conf, 3),
        "final_confidence":      round(final_conf, 3),
        "confidence_label":      label,
        "calibration_adjustments": [
            {"delta": round(a, 3), "reason": r} for a, r in adjustments
        ],
    }


def _conf_label(conf: float) -> str:
    if conf >= 0.75:
        return "high"
    elif conf >= 0.55:
        return "medium"
    elif conf >= 0.40:
        return "low"
    return "very_low"
