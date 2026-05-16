"""
intelligence_layer/research_target_planner/layer6_runner.py — Layer 6

Main controller for the Research Target Planner.
Pure rule-based pipeline — no LLM calls.

Pipeline (11 steps):
  1.  Load planning inputs (L3 + L4 + L5)
  2.  Filter opportunities (secondary pass)
  3.  Build target candidates
  4.  Classify types + resolve entities + resolve tickers + preserve unresolved
  5.  Map proxies / sector constituents / macro targets / fund vehicles
  6.  Deduplicate resolved candidates
  7.  Score target priority
  8.  Apply selection policy (select / defer / watch / reject)
  9.  Assign deep-dive depth + map to collector modules
  10. Build deep_dive_plan.json
  11. Run guardrail check + write all outputs

Run standalone:
    python intelligence_layer/research_target_planner/layer6_runner.py
    python intelligence_layer/research_target_planner/layer6_runner.py --date 2026-05-10

Design doc: docs/system_design_docs/layer_6.md §1 layer6_runner.py
"""

from __future__ import annotations
import argparse
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import LAYER3_DIR, LAYER4_DIR, LAYER5_DIR, LAYER6_DIR

from intelligence_layer.research_target_planner import (
    planning_input_loader,
    opportunity_filter,
    target_candidate_builder,
    target_type_classifier,
    entity_resolver,
    ticker_resolver,
    unresolved_entity_preserver,
    proxy_mapper,
    sector_constituent_mapper,
    macro_target_mapper,
    fund_vehicle_mapper,
    target_deduplicator,
    target_priority_scorer,
    target_selection_policy,
    deep_dive_depth_controller,
    deep_dive_module_mapper,
    deep_dive_plan_builder,
    target_guardrail_validator,
    research_target_bundle_builder,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer3_dir: Path, layer4_dir: Path, layer5_dir: Path,
        layer6_dir: Path, run_id: str) -> dict:
    """Execute the full Layer 6 pipeline. Returns manifest dict."""
    print(f"\n{'='*60}")
    print(f"Layer 6 — Research Target Planner")
    print(f"Run ID  : {run_id}")
    print(f"L3 dir  : {layer3_dir}")
    print(f"L4 dir  : {layer4_dir}")
    print(f"L5 dir  : {layer5_dir}")
    print(f"L6 dir  : {layer6_dir}")
    print(f"{'='*60}\n")

    # ── Step 1: Load planning inputs ─────────────────────────────────────────
    print("[1/11] Loading planning inputs (L3 + L4 + L5)...")
    ctx = planning_input_loader.load(layer3_dir, layer4_dir, layer5_dir)
    ls  = ctx["load_summary"]
    print(f"       L6-bound hypotheses: {ls['l6_bound_hypotheses']} / {ls['all_hypotheses']}")
    print(f"       entity_registry: {ls['entity_registry_size']} | market_view regime: {ctx['market_view'].get('regime')}")

    # ── Step 2: Filter opportunities ─────────────────────────────────────────
    print("[2/11] Filtering opportunities...")
    filt = opportunity_filter.filter_opportunities(ctx["opportunity_hypotheses"])
    print(f"       accepted={len(filt['accepted'])} deferred={len(filt['deferred'])} rejected={len(filt['rejected'])}")

    # ── Step 3: Build target candidates ──────────────────────────────────────
    print("[3/11] Building target candidates...")
    candidates = target_candidate_builder.build_candidates(filt["accepted"])
    print(f"       {len(candidates)} candidates from {len(filt['accepted'])} hypotheses")

    # ── Step 4: Classify + resolve ────────────────────────────────────────────
    print("[4/11] Classifying types + resolving entities + tickers...")
    candidates = target_type_classifier.classify_all(candidates)
    candidates = entity_resolver.resolve_all(candidates, ctx["entity_by_ticker"], ctx["entity_by_norm"])
    candidates = ticker_resolver.resolve_all(candidates)
    resolved, unresolved = unresolved_entity_preserver.preserve_unresolved(candidates)
    from collections import Counter
    type_counts = Counter(c["target_type"] for c in candidates)
    print(f"       types: {dict(type_counts)}")
    print(f"       resolved (ticker): {len(resolved)} | unresolved: {len(unresolved)}")

    # ── Step 5: Proxy / sector / macro / fund mapping ─────────────────────────
    print("[5/11] Mapping proxies / sector constituents / macro targets...")
    proxy_mappings   = proxy_mapper.map_proxies(unresolved, candidates, ctx["opportunity_hypotheses"])
    sector_mappings  = sector_constituent_mapper.map_sectors(unresolved)
    macro_mappings   = macro_target_mapper.map_macro_targets(unresolved)
    fund_mappings    = fund_vehicle_mapper.map_fund_vehicles(unresolved)
    print(f"       proxy={len(proxy_mappings)} sector={len(sector_mappings)} macro={len(macro_mappings)} fund={len(fund_mappings)}")

    # ── Step 6: Deduplicate resolved candidates ───────────────────────────────
    print("[6/11] Deduplicating targets...")
    deduped = target_deduplicator.deduplicate(resolved)
    print(f"       {len(resolved)} resolved → {len(deduped)} unique targets after dedup")

    # ── Step 7: Score priority ────────────────────────────────────────────────
    print("[7/11] Scoring target priority...")
    scores = target_priority_scorer.score_all(deduped, ctx["opportunity_hypotheses"], ctx["market_view"])
    label_counts = Counter(s["priority_label"] for s in scores)
    print(f"       {dict(label_counts)}")

    # ── Step 8: Apply selection policy ────────────────────────────────────────
    print("[8/11] Applying selection policy...")
    selection = target_selection_policy.apply_policy(deduped, scores)
    selected  = selection["selected"]
    deferred  = selection["deferred"]
    watch     = selection["watch"]
    rejected  = selection["rejected"]
    print(f"       selected={len(selected)} deferred={len(deferred)} watch={len(watch)} rejected={len(rejected)}")

    # ── Step 9: Depth + module mapping ────────────────────────────────────────
    print("[9/11] Assigning research depth + mapping modules...")
    selected = deep_dive_depth_controller.assign_depth_all(selected)
    module_task_map: dict[str, list[dict]] = {}
    for t in selected:
        tasks = deep_dive_module_mapper.map_modules(t)
        module_task_map[t["target_id"]] = tasks
    total_tasks = sum(len(v) for v in module_task_map.values())
    depth_counts = Counter(t.get("deep_dive_depth", "?") for t in selected)
    print(f"       depth: {dict(depth_counts)} | total tasks: {total_tasks}")

    # ── Step 10: Build deep_dive_plan ─────────────────────────────────────────
    print("[10/11] Building deep_dive_plan.json...")
    dd_plan = deep_dive_plan_builder.build_plan(selected, module_task_map, ctx["research_run_id"])
    print(f"        plan_id={dd_plan['deep_dive_plan_id']} targets={dd_plan['total_targets']} tasks={dd_plan['total_tasks']}")

    # ── Step 11: Guardrail check + write outputs ──────────────────────────────
    print("[11/11] Running guardrail check + writing outputs...")
    guardrail_results = target_guardrail_validator.check_all(selected, proxy_mappings)
    selected = target_guardrail_validator.apply_guardrail_decisions(selected, guardrail_results)
    gr_pass  = sum(1 for r in guardrail_results if r.get("status") == "pass")
    gr_flag  = len(guardrail_results) - gr_pass
    print(f"        guardrail: {gr_pass} pass | {gr_flag} flagged/downgraded")

    manifest = research_target_bundle_builder.build_and_write(
        layer6_dir=layer6_dir,
        run_id=ctx["research_run_id"],
        all_candidates=candidates,
        selected_targets=selected,
        deferred_targets=deferred,
        watch_targets=watch,
        rejected_targets=rejected,
        unresolved_entities=unresolved,
        proxy_mappings=proxy_mappings,
        sector_mappings=sector_mappings,
        macro_mappings=macro_mappings,
        guardrail_results=guardrail_results,
        deep_dive_plan=dd_plan,
        opportunity_filter_result=filt,
        load_summary=ls,
    )

    print(f"\n{'='*60}")
    print(f"Layer 6 complete.")
    print(f"  Target candidates  : {len(candidates)}")
    print(f"  Unique targets     : {len(deduped)}")
    print(f"  Selected           : {len(selected)}")
    print(f"  Deferred           : {len(deferred)}")
    print(f"  Deep-dive tasks    : {total_tasks}")
    print(f"  Output dir         : {layer6_dir}")
    print(f"{'='*60}\n")

    return manifest


def _build_run_id(target_date: str) -> str:
    now = datetime.now(_IST).strftime("%H%M")
    return f"RUN_{target_date.replace('-', '_')}_AUTONOMOUS_DAILY_{now}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 6 — Research Target Planner")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target_date = args.date
    base_out    = Path(__file__).parent.parent.parent / "output" / target_date

    layer3_dir = base_out / "layer3"
    layer4_dir = base_out / "layer4"
    layer5_dir = base_out / "layer5"
    layer6_dir = base_out / "layer6"

    if not layer3_dir.exists():
        print(f"ERROR: Layer 3 output not found at {layer3_dir}", file=sys.stderr)
        sys.exit(1)
    if not layer5_dir.exists():
        print(f"ERROR: Layer 5 output not found at {layer5_dir}", file=sys.stderr)
        sys.exit(1)

    run_id = _build_run_id(target_date)
    run(layer3_dir, layer4_dir, layer5_dir, layer6_dir, run_id)


if __name__ == "__main__":
    main()
