"""
intelligence_layer/research_target_planner/target_priority_scorer.py — Layer 6

Scores each target's priority for deep-dive research using 9 dimensions.
Uses evidence from merged_count (how many hypotheses named this target),
confidence, time_horizon, ticker resolution, and data gaps.

Score range: 0-100 (can slightly exceed due to additive dims before penalty)

Labels:
  >= 80 → high_priority_deep_dive
  65-79 → standard_deep_dive
  50-64 → light_or_defer
  35-49 → watch_only
  < 35  → reject

Design doc: docs/system_design_docs/layer_6.md §14 target_priority_scorer.py
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_HORIZON_TIME_SCORE = {
    "short_term":  10,
    "medium_term": 7,
    "long_term":   4,
    "structural":  2,
}

_TYPE_ACTIONABILITY = {
    "listed_company":           15,
    "sector_theme":             8,
    "macro_theme":              5,
    "fund_etf":                 6,
    "private_unlisted_company": 4,
    "commodity":                4,
    "real_estate_regional_theme": 3,
    "unknown":                  1,
}

_TYPE_MAPPABILITY = {
    "listed_company":           10,
    "sector_theme":             5,
    "macro_theme":              3,
    "fund_etf":                 5,
    "private_unlisted_company": 2,
}


def score_all(targets: list[dict], opportunity_hypotheses: list[dict],
              market_view: dict) -> list[dict]:
    """
    Score all targets. Returns list of score dicts (one per target).
    """
    today = datetime.now(_IST).strftime("%Y%m%d")
    hyp_by_id = {h["opportunity_id"]: h for h in opportunity_hypotheses}
    favored_sectors = set((market_view.get("sectors") or {}).get("favored") or [])

    scores: list[dict] = []
    for i, t in enumerate(targets, 1):
        _CTR[0] += 1
        breakdown, total = _score_target(t, hyp_by_id, favored_sectors)
        total = max(0, min(100, total))

        if total >= 80:
            label = "high_priority_deep_dive"
        elif total >= 65:
            label = "standard_deep_dive"
        elif total >= 50:
            label = "light_or_defer"
        elif total >= 35:
            label = "watch_only"
        else:
            label = "reject"

        scores.append({
            "target_score_id":        f"TSCORE_{today}_{_CTR[0]:04d}",
            "target_id":              t.get("target_id", ""),
            "target_name":            t.get("target_name", ""),
            "ticker":                 t.get("ticker"),
            "target_type":            t.get("target_type", ""),
            "priority_score":         total,
            "priority_label":         label,
            "score_breakdown":        breakdown,
            "confidence":             t.get("confidence", 0.5),
        })

    return scores


def attach_scores(targets: list[dict], scores: list[dict]) -> list[dict]:
    """Attach score info onto target dicts in-place."""
    score_map = {s["target_id"]: s for s in scores}
    for t in targets:
        s = score_map.get(t["target_id"], {})
        t["priority_score"] = s.get("priority_score", 0)
        t["priority_label"] = s.get("priority_label", "reject")
    return targets


def _score_target(t: dict, hyp_by_id: dict, favored_sectors: set) -> tuple[dict, int]:
    merged_count  = t.get("merged_count", 1)
    confidence    = t.get("confidence", 0.5)
    time_horizon  = t.get("time_horizon", "medium_term")
    target_type   = t.get("target_type", "unknown")
    ticker        = t.get("ticker")
    data_gaps     = t.get("data_gaps") or []
    opp_ids       = t.get("source_opportunity_ids") or []
    supporting    = t.get("supporting_refs") or []

    # Pull hypothesis-level data for source hypotheses
    hyps = [hyp_by_id[oid] for oid in opp_ids if oid in hyp_by_id]
    avg_strength_score = (
        sum(h.get("_priority_score", 50) for h in hyps) / len(hyps) if hyps else 50
    )
    has_memory = any(h.get("origin", {}).get("memory_refs") for h in hyps)
    high_strength_count = sum(1 for h in hyps if h.get("hypothesis_strength") == "high")

    # ── Dimensions ───────────────────────────────────────────────────────────
    # 1. Opportunity strength (0-20): confidence × 20 + bonus for high-strength hyps
    opp_strength = min(int(confidence * 16) + min(high_strength_count * 2, 4), 20)

    # 2. Event materiality (0-15): based on how many hypotheses and source refs
    event_mat = min(len(opp_ids) * 3 + len(supporting) * 1, 15)

    # 3. Source reliability (0-15): proxy via avg L5 strength score
    src_reliability = min(int(avg_strength_score / 7), 15)

    # 4. Source diversity (0-10): merged_count (number of hypotheses naming this target)
    src_diversity = min(merged_count * 2, 10)

    # 5. Memory recurrence (0-10)
    memory_rec = 8 if has_memory else 0

    # 6. Target actionability (0-15)
    actionability = _TYPE_ACTIONABILITY.get(target_type, 1)

    # 7. Ticker/proxy mappability (0-10)
    ticker_map = 10 if ticker else _TYPE_MAPPABILITY.get(target_type, 0)

    # 8. Time sensitivity (0-10)
    time_sens = _HORIZON_TIME_SCORE.get(time_horizon, 5)

    # 9. Data gap penalty (0-15)
    gap_penalty = -min(len(data_gaps) * 2, 15)

    # 10. Speculation penalty
    low_strength_hyps = sum(1 for h in hyps if h.get("hypothesis_strength") == "low")
    spec_penalty = -min(low_strength_hyps * 5, 15)

    total = (opp_strength + event_mat + src_reliability + src_diversity
             + memory_rec + actionability + ticker_map + time_sens
             + gap_penalty + spec_penalty)

    breakdown = {
        "opportunity_strength":    opp_strength,
        "event_materiality":       event_mat,
        "source_reliability":      src_reliability,
        "source_diversity":        src_diversity,
        "memory_recurrence":       memory_rec,
        "target_actionability":    actionability,
        "ticker_mappability":      ticker_map,
        "time_sensitivity":        time_sens,
        "data_gap_penalty":        gap_penalty,
        "speculation_penalty":     spec_penalty,
    }

    return breakdown, total


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import (
        planning_input_loader, opportunity_filter, target_candidate_builder,
        target_type_classifier, entity_resolver, ticker_resolver,
        unresolved_entity_preserver, target_deduplicator)

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / date
    ctx  = planning_input_loader.load(base / "layer3", base / "layer4", base / "layer5")
    filt = opportunity_filter.filter_opportunities(ctx["opportunity_hypotheses"])
    cands = target_candidate_builder.build_candidates(filt["accepted"])
    cands = target_type_classifier.classify_all(cands)
    cands = entity_resolver.resolve_all(cands, ctx["entity_by_ticker"], ctx["entity_by_norm"])
    cands = ticker_resolver.resolve_all(cands)
    resolved, _ = unresolved_entity_preserver.preserve_unresolved(cands)
    deduped = target_deduplicator.deduplicate(resolved)

    scores = score_all(deduped, ctx["opportunity_hypotheses"], ctx["market_view"])
    scores_sorted = sorted(scores, key=lambda s: s["priority_score"], reverse=True)

    print(f"Scored targets: {len(scores)}")
    print()
    print("Top 10 by priority score:")
    for s in scores_sorted[:10]:
        print(f"  [{s['priority_score']:3d}] {s['target_name'][:40]:<40} {s['priority_label']}")
    print()
    from collections import Counter
    labels = Counter(s["priority_label"] for s in scores)
    for lbl, cnt in labels.most_common():
        print(f"  {lbl}: {cnt}")
