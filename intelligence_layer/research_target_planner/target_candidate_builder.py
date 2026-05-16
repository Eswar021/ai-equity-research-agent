"""
intelligence_layer/research_target_planner/target_candidate_builder.py — Layer 6

Converts accepted opportunity hypotheses into target candidates.
Each hypothesis can produce multiple candidates:
  1. One candidate per likely_beneficiaries_or_targets entry
  2. One self-candidate for sector_theme / macro_theme hypotheses (the theme itself)

Design doc: docs/system_design_docs/layer_6.md §4 target_candidate_builder.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_SELF_TARGET_OPP_TYPES = {
    "sector_theme", "macro_theme", "cross_domain",
    "real_estate_theme", "fund_etf", "commodity",
}


def build_candidates(accepted_hypotheses: list[dict]) -> list[dict]:
    """
    Build target candidates from accepted L5 hypotheses.
    Returns flat list of candidate dicts.
    """
    candidates: list[dict] = []
    today = datetime.now(_IST).strftime("%Y%m%d")

    for h in accepted_hypotheses:
        opp_id        = h.get("opportunity_id", "")
        opp_type      = h.get("opportunity_type", "")
        opp_title     = h.get("opportunity_title", "")
        time_horizon  = h.get("time_horizon", "medium_term")
        confidence    = h.get("confidence", 0.5)
        supporting    = h.get("supporting_refs") or []
        data_gaps     = h.get("data_gaps") or []
        origin        = h.get("origin") or {}
        beneficiaries = h.get("likely_beneficiaries_or_targets") or []
        deep_dive_qs  = h.get("required_deep_dive_questions") or []

        # combined refs for traceability (supporting_refs are dicts; origin refs are strings)
        all_refs = (origin.get("event_refs") or [])[:3] + (origin.get("theme_refs") or [])[:2]
        # keep up to 3 source doc IDs from supporting_refs
        for sr in supporting[:3]:
            cid = sr.get("chunk_id") or sr.get("document_id") if isinstance(sr, dict) else str(sr)
            if cid and cid not in all_refs:
                all_refs.append(cid)

        # ── 1. One candidate per beneficiary ─────────────────────────────────
        for b in beneficiaries:
            _CTR[0] += 1
            cand_id = f"TCAND_{today}_{_CTR[0]:04d}"
            candidates.append({
                "candidate_target_id":   cand_id,
                "source_opportunity_id": opp_id,
                "source_opportunity_type": opp_type,
                "candidate_name":        b.get("entity_name", ""),
                "candidate_type_hint":   b.get("target_type", ""),
                "ticker_hint":           b.get("ticker") or "",
                "mapping_status_hint":   b.get("mapping_status", ""),
                "market":                "india",
                "time_horizon":          time_horizon,
                "why_candidate":         [
                    f"Beneficiary in: {opp_title[:80]}",
                    f"Opportunity type: {opp_type}",
                ],
                "questions_to_answer":   deep_dive_qs[:3],
                "supporting_refs":       all_refs,
                "data_gaps":             data_gaps,
                "confidence":            confidence,
                "origin_signal_group":   origin.get("signal_group_id", ""),
            })

        # ── 2. Self-candidate for sector/macro/theme hypotheses ───────────────
        if opp_type in _SELF_TARGET_OPP_TYPES:
            _CTR[0] += 1
            cand_id = f"TCAND_{today}_{_CTR[0]:04d}"
            candidates.append({
                "candidate_target_id":   cand_id,
                "source_opportunity_id": opp_id,
                "source_opportunity_type": opp_type,
                "candidate_name":        opp_title[:100],
                "candidate_type_hint":   opp_type,          # sector_theme | macro_theme | etc.
                "ticker_hint":           "",
                "mapping_status_hint":   "theme_level",
                "market":                "india",
                "time_horizon":          time_horizon,
                "why_candidate":         [
                    f"Theme/macro target from hypothesis: {opp_title[:60]}",
                    "No single ticker — requires sector/macro research path",
                ],
                "questions_to_answer":   deep_dive_qs[:3],
                "supporting_refs":       all_refs,
                "data_gaps":             data_gaps,
                "confidence":            confidence * 0.9,   # slight discount: no specific entity
                "origin_signal_group":   origin.get("signal_group_id", ""),
            })

    return candidates


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import planning_input_loader, opportunity_filter

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / date
    ctx  = planning_input_loader.load(base / "layer3", base / "layer4", base / "layer5")
    filt = opportunity_filter.filter_opportunities(ctx["opportunity_hypotheses"])

    candidates = build_candidates(filt["accepted"])
    print(f"Accepted hypotheses : {len(filt['accepted'])}")
    print(f"Total candidates    : {len(candidates)}")
    print(f"  from beneficiaries  : {sum(1 for c in candidates if 'Beneficiary' in c['why_candidate'][0])}")
    print(f"  self (theme/macro)  : {sum(1 for c in candidates if 'theme_level' in c.get('mapping_status_hint',''))}")
    print()
    for c in candidates[:4]:
        print(f"  [{c['candidate_target_id']}] {c['candidate_name'][:50]!r} ticker={c['ticker_hint']!r} type_hint={c['candidate_type_hint']!r}")
