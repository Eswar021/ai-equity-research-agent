"""
intelligence_layer/research_target_planner/target_selection_policy.py — Layer 6

Decides each target's fate: selected | deferred | watch | rejected.
Enforces budget caps to prevent deep-diving everything.

Thresholds:
  >= 65 → selected_for_deep_dive (up to budget caps)
  50-64 → deferred
  35-49 → watch_only
  < 35  → rejected

Budget caps (configurable via layer6_config):
  max_selected            = 12
  max_listed_company      = 7
  max_sector_theme        = 3
  max_macro               = 2

Design doc: docs/system_design_docs/layer_6.md §15 target_selection_policy.py
"""

from __future__ import annotations

_DEFAULT_CONFIG = {
    "max_selected_targets":       12,
    "max_listed_company_targets": 7,
    "max_sector_theme_targets":   3,
    "max_macro_targets":          2,
    "min_score_for_selection":    65,
    "min_score_for_defer":        50,
    "min_score_for_watch":        35,
}


def apply_policy(targets: list[dict], scores: list[dict],
                 layer6_config: dict | None = None) -> dict:
    """
    Apply selection policy to all targets.
    Returns {"selected": [...], "deferred": [...], "watch": [...], "rejected": [...]}.
    Each target gets selection_status + selection_reason.
    """
    cfg = {**_DEFAULT_CONFIG, **(layer6_config or {})}

    score_map = {s["target_id"]: s for s in scores}

    # Sort by priority score descending
    sorted_targets = sorted(
        targets,
        key=lambda t: score_map.get(t["target_id"], {}).get("priority_score", 0),
        reverse=True,
    )

    selected: list[dict] = []
    deferred: list[dict] = []
    watch:    list[dict] = []
    rejected: list[dict] = []

    # Track budget consumption
    budgets = {
        "total":        0,
        "listed_company": 0,
        "sector_theme": 0,
        "macro_theme":  0,
    }

    for t in sorted_targets:
        score_info = score_map.get(t["target_id"], {})
        score      = score_info.get("priority_score", 0)
        ttype      = t.get("target_type", "unknown")
        t_id       = t.get("target_id", "")

        # Attach score to target
        t["priority_score"] = score
        t["priority_label"] = score_info.get("priority_label", "reject")

        if score < cfg["min_score_for_watch"]:
            t["selection_status"] = "rejected"
            t["selection_reason"] = [f"Score {score} below reject threshold {cfg['min_score_for_watch']}"]
            rejected.append(t)
            continue

        if score < cfg["min_score_for_defer"]:
            t["selection_status"] = "watch_only"
            t["selection_reason"] = [f"Score {score} — interesting but insufficient for deep dive"]
            watch.append(t)
            continue

        if score < cfg["min_score_for_selection"]:
            t["selection_status"] = "deferred"
            t["selection_reason"] = [f"Score {score} — moderate priority, deferred for next run"]
            deferred.append(t)
            continue

        # Score qualifies for selection — check budget
        if budgets["total"] >= cfg["max_selected_targets"]:
            t["selection_status"] = "deferred"
            t["selection_reason"] = [f"Total target budget ({cfg['max_selected_targets']}) reached"]
            deferred.append(t)
            continue

        type_budget_key = ttype if ttype in ("listed_company", "sector_theme", "macro_theme") else None
        type_cap = {
            "listed_company": cfg["max_listed_company_targets"],
            "sector_theme":   cfg["max_sector_theme_targets"],
            "macro_theme":    cfg["max_macro_targets"],
        }.get(ttype)

        if type_cap is not None and budgets.get(ttype, 0) >= type_cap:
            t["selection_status"] = "deferred"
            t["selection_reason"] = [f"{ttype} budget ({type_cap}) reached; score={score}"]
            deferred.append(t)
            continue

        # Select
        t["selection_status"] = "selected_for_deep_dive"
        t["selection_reason"] = [
            f"Score {score} qualifies for deep dive",
            f"Type: {ttype}",
        ]
        selected.append(t)
        budgets["total"] += 1
        if type_budget_key:
            budgets[type_budget_key] = budgets.get(type_budget_key, 0) + 1

    return {
        "selected": selected,
        "deferred": deferred,
        "watch":    watch,
        "rejected": rejected,
    }


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import (
        planning_input_loader, opportunity_filter, target_candidate_builder,
        target_type_classifier, entity_resolver, ticker_resolver,
        unresolved_entity_preserver, target_deduplicator, target_priority_scorer)

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
    scores  = target_priority_scorer.score_all(deduped, ctx["opportunity_hypotheses"], ctx["market_view"])

    result = apply_policy(deduped, scores)
    print(f"Selected : {len(result['selected'])}")
    print(f"Deferred : {len(result['deferred'])}")
    print(f"Watch    : {len(result['watch'])}")
    print(f"Rejected : {len(result['rejected'])}")
    print()
    print("Selected targets:")
    for t in result["selected"]:
        print(f"  [{t['priority_score']:3d}] {t['target_name'][:40]:<40} ticker={t.get('ticker','')}")
