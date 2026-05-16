"""
intelligence_layer/research_target_planner/opportunity_filter.py — Layer 6

Secondary filter on L6-bound hypotheses.
planning_input_loader already filtered by send_to_layer6=True + guardrail_status=pass.
This module further culls:
  - ACCEPT:  requires_deep_dive=True with beneficiaries, OR sector/macro types
  - DEFER:   interesting but hypothesis_strength=low and many data_gaps
  - REJECT:  no beneficiaries AND not sector/macro AND not requires_deep_dive

Design doc: docs/system_design_docs/layer_6.md §3 opportunity_filter.py
"""

from __future__ import annotations

_SECTOR_MACRO_TYPES = {"sector_theme", "macro_theme", "cross_domain", "real_estate_theme"}
_MIN_CONFIDENCE     = 0.35


def filter_opportunities(hypotheses: list[dict]) -> dict:
    """
    Secondary filter on L6-bound hypotheses.
    Returns {"accepted": [...], "deferred": [...], "rejected": [...]}.
    Each item gets filter_status + filter_reason.
    """
    accepted: list[dict] = []
    deferred: list[dict] = []
    rejected: list[dict] = []

    for h in hypotheses:
        opp_type     = h.get("opportunity_type", "")
        beneficiaries = h.get("likely_beneficiaries_or_targets") or []
        requires_dd   = h.get("requires_deep_dive", False)
        confidence    = h.get("confidence", 0.5)
        data_gaps     = h.get("data_gaps") or []
        strength      = h.get("hypothesis_strength", "medium")
        supporting    = h.get("supporting_refs") or []

        is_sector_macro = opp_type in _SECTOR_MACRO_TYPES or "sector" in opp_type or "macro" in opp_type

        # Reject: below minimum confidence
        if confidence < _MIN_CONFIDENCE:
            h["filter_status"] = "rejected"
            h["filter_reason"] = f"Confidence {confidence:.2f} below threshold {_MIN_CONFIDENCE}"
            rejected.append(h)
            continue

        # Reject: no evidence trail and not a structural theme
        if not supporting and not beneficiaries and not is_sector_macro:
            h["filter_status"] = "rejected"
            h["filter_reason"] = "No supporting_refs and no beneficiaries"
            rejected.append(h)
            continue

        # Reject: no investable path at all (no beneficiaries, not sector/macro, not deep_dive)
        if not beneficiaries and not is_sector_macro and not requires_dd:
            h["filter_status"] = "rejected"
            h["filter_reason"] = "No beneficiaries and not sector/macro type"
            rejected.append(h)
            continue

        # Defer: low strength + many data gaps → interesting but premature
        if strength == "low" and len(data_gaps) >= 3:
            h["filter_status"] = "deferred"
            h["filter_reason"] = f"Low strength with {len(data_gaps)} data gaps — premature for deep dive"
            deferred.append(h)
            continue

        # Accept everything else
        h["filter_status"] = "accepted"
        h["filter_reason"]  = "Research-worthy and evidence-backed"
        accepted.append(h)

    return {"accepted": accepted, "deferred": deferred, "rejected": rejected}


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import planning_input_loader

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / date
    ctx  = planning_input_loader.load(base / "layer3", base / "layer4", base / "layer5")

    result = filter_opportunities(ctx["opportunity_hypotheses"])
    print(f"Accepted : {len(result['accepted'])}")
    print(f"Deferred : {len(result['deferred'])}")
    print(f"Rejected : {len(result['rejected'])}")
    print("\nDeferred reasons:")
    for h in result["deferred"][:3]:
        print(f"  [{h['opportunity_id']}] {h['filter_reason']}")
    print("\nRejected reasons:")
    for h in result["rejected"][:3]:
        print(f"  [{h['opportunity_id']}] {h['filter_reason']}")
