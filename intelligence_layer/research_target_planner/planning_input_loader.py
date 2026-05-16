"""
intelligence_layer/research_target_planner/planning_input_loader.py — Layer 6

Loads all planning inputs from Layers 3, 4, and 5.
Filters hypotheses to those marked send_to_layer6=True with guardrail_status=pass.
Builds lookup indexes for fast access.

Design doc: docs/system_design_docs/layer_6.md §2 planning_input_loader.py
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer3_dir: Path, layer4_dir: Path, layer5_dir: Path) -> dict:
    """
    Load and index all planning inputs from Layers 3, 4, 5.
    Returns a planning_context dict used by all downstream L6 modules.
    """
    layer3_dir = Path(layer3_dir)
    layer4_dir = Path(layer4_dir)
    layer5_dir = Path(layer5_dir)

    # ── Layer 5 ───────────────────────────────────────────────────────────────
    all_hypotheses    = _load(layer5_dir / "opportunity_hypotheses.json")
    strength_scores   = _load(layer5_dir / "hypothesis_strength_scores.json")
    guardrail_results = _load(layer5_dir / "guardrail_results.json")
    sector_theme_views = _load(layer5_dir / "sector_theme_views.json")
    event_impact_views = _load(layer5_dir / "event_impact_views.json")
    signal_groups      = _load(layer5_dir / "signal_groups.json")
    market_view        = _load_single(layer5_dir / "market_view.json")
    l5_manifest        = _load_single(layer5_dir / "layer5_manifest.json")

    # ── Layer 3 ───────────────────────────────────────────────────────────────
    entity_registry = _load(layer3_dir / "entity_registry.json")

    # ── Layer 4 memory context ────────────────────────────────────────────────
    memory_context  = _load_single(layer4_dir / "memory_context_packet.json")

    # ── Build lookup indexes ──────────────────────────────────────────────────
    score_by_id    = {s["opportunity_id"]: s for s in strength_scores}
    guardrail_by_id = {r["object_id"]: r for r in guardrail_results}
    stv_by_grp     = {v["signal_group_id"]: v for v in sector_theme_views}
    eiv_by_event   = {v["event_id"]: v for v in event_impact_views}
    sig_by_id      = {g["signal_group_id"]: g for g in signal_groups}

    # Entity lookups
    entity_by_ticker: dict[str, dict] = {}
    entity_by_norm:   dict[str, dict] = {}
    for e in entity_registry:
        if e.get("ticker"):
            entity_by_ticker[e["ticker"].upper()] = e
        norm = e.get("normalized_name", "").lower().strip()
        if norm:
            entity_by_norm[norm] = e
        # also index by raw entity_name for quick lookup
        raw = e.get("entity_name", "").lower().strip()
        if raw and raw not in entity_by_norm:
            entity_by_norm[raw] = e

    # ── Filter to L6-bound hypotheses ─────────────────────────────────────────
    l6_hypotheses: list[dict] = []
    for h in all_hypotheses:
        oid   = h.get("opportunity_id", "")
        score = score_by_id.get(oid, {})
        gr    = guardrail_by_id.get(oid, {})
        if score.get("send_to_layer6") and h.get("guardrail_status") == "pass":
            # Attach score and guardrail summaries inline
            h["_priority_score"]   = score.get("hypothesis_strength_score", 0)
            h["_strength_label"]   = score.get("strength_label", "")
            h["_score_breakdown"]  = score.get("score_breakdown", {})
            l6_hypotheses.append(h)

    run_id = l5_manifest.get("research_run_id", "UNKNOWN")

    load_summary = {
        "run_id":                    run_id,
        "all_hypotheses":            len(all_hypotheses),
        "l6_bound_hypotheses":       len(l6_hypotheses),
        "entity_registry_size":      len(entity_registry),
        "sector_theme_views":        len(sector_theme_views),
        "event_impact_views":        len(event_impact_views),
        "signal_groups":             len(signal_groups),
        "memory_context_loaded":     bool(memory_context),
    }

    return {
        "research_run_id":    run_id,
        "market_view":        market_view,
        "opportunity_hypotheses":  l6_hypotheses,
        "all_hypotheses":     all_hypotheses,
        "score_by_id":        score_by_id,
        "guardrail_by_id":    guardrail_by_id,
        "stv_by_grp":         stv_by_grp,
        "eiv_by_event":       eiv_by_event,
        "sig_by_id":          sig_by_id,
        "entity_registry":    entity_registry,
        "entity_by_ticker":   entity_by_ticker,
        "entity_by_norm":     entity_by_norm,
        "memory_context":     memory_context,
        "load_summary":       load_summary,
    }


def _load(path: Path) -> list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_single(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from datetime import date
    from pathlib import Path

    sys.path.append(str(Path(__file__).parent.parent.parent))

    target_date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / target_date

    ctx = load(base / "layer3", base / "layer4", base / "layer5")
    ls  = ctx["load_summary"]
    print(f"Run ID  : {ctx['research_run_id']}")
    print(f"L6-bound hypotheses : {ls['l6_bound_hypotheses']} / {ls['all_hypotheses']}")
    print(f"Entity registry     : {ls['entity_registry_size']}")
    print(f"Market view regime  : {ctx['market_view'].get('regime')}")
    print(f"Memory context      : {'loaded' if ls['memory_context_loaded'] else 'missing'}")
    print()
    h0 = ctx["opportunity_hypotheses"][0]
    print(f"First L6 hyp: [{h0['opportunity_id']}] {h0['opportunity_title'][:70]}")
    print(f"  strength={h0['hypothesis_strength']} score={h0['_priority_score']} beneficiaries={len(h0.get('likely_beneficiaries_or_targets',[]))}")
