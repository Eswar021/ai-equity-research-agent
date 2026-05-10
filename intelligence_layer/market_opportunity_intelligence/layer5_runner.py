"""
intelligence_layer/market_opportunity_intelligence/layer5_runner.py — Layer 5

Main controller for Market & Opportunity Intelligence.

Pipeline:
  1.  Load Layer 3 + Layer 4 intelligence via intelligence_memory_loader
  2.  Aggregate signals into ~30-50 signal groups via signal_aggregator
  3.  Build market view via market_regime_agent
  4.  Classify event impacts via event_impact_classifier
  5.  Analyze sector/theme intelligence via sector_theme_agent
  6.  Generate opportunity hypotheses via opportunity_hypothesis_generator (LLM)
  7.  Map cross-domain chains via cross_domain_mapper (deferred → empty list)
  8.  Classify time horizons via time_horizon_classifier
  9.  Score hypothesis strength via hypothesis_strength_scorer
  10. Run guardrail precheck via layer5_guardrail_precheck
  11. Write all outputs via market_opportunity_bundle_builder

Run standalone:
    python intelligence_layer/market_opportunity_intelligence/layer5_runner.py
    python intelligence_layer/market_opportunity_intelligence/layer5_runner.py --date 2026-05-10
    python intelligence_layer/market_opportunity_intelligence/layer5_runner.py --provider gemini

Design doc: docs/system_design_docs/layer_5.md §1 layer5_runner.py
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import LAYER3_DIR, LAYER4_DIR, LAYER5_DIR, OUTPUT_DIR
from llm.llm_client import make_llm

from intelligence_layer.market_opportunity_intelligence import (
    intelligence_memory_loader,
    signal_aggregator,
    market_regime_agent,
    event_impact_classifier,
    sector_theme_agent,
    opportunity_hypothesis_generator,
    cross_domain_mapper,
    time_horizon_classifier,
    hypothesis_strength_scorer,
    layer5_guardrail_precheck,
    market_opportunity_bundle_builder,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer3_dir: Path, layer4_dir: Path, layer5_dir: Path,
        run_id: str, provider: str) -> dict:
    """
    Execute the full Layer 5 pipeline.
    Returns the manifest dict written by the bundle builder.
    """
    print(f"\n{'='*60}")
    print(f"Layer 5 — Market & Opportunity Intelligence")
    print(f"Run ID  : {run_id}")
    print(f"L3 dir  : {layer3_dir}")
    print(f"L4 dir  : {layer4_dir}")
    print(f"L5 dir  : {layer5_dir}")
    print(f"Provider: {provider}")
    print(f"{'='*60}\n")

    # ── Step 1: Load intelligence ─────────────────────────────────────────────
    print("[1/11] Loading Layer 3 + Layer 4 intelligence...")
    intelligence = intelligence_memory_loader.load(layer3_dir, layer4_dir)
    ls = intelligence["load_summary"]
    print(f"       entities={ls['entities']} facts={ls['facts']} claims={ls['claims']} "
          f"events={ls['events']} themes={ls['themes']} signals={ls['market_signals']}")
    print(f"       memory: short={ls['memory_short_term']} watch={ls['memory_watch']} "
          f"long={ls['memory_long_term']} theses={ls['active_theses']}")

    # ── Step 2: Aggregate signals ─────────────────────────────────────────────
    print("[2/11] Aggregating signals into signal groups...")
    signal_groups = signal_aggregator.aggregate(intelligence)
    theme_grps    = sum(1 for g in signal_groups if g["group_type"] == "theme_centric")
    entity_grps   = sum(1 for g in signal_groups if g["group_type"] == "entity_centric")
    mkt_grps      = sum(1 for g in signal_groups if g["group_type"] == "market_signal")
    print(f"       {len(signal_groups)} groups: {theme_grps} theme | {entity_grps} entity | {mkt_grps} market")

    # ── Step 3: Market view ───────────────────────────────────────────────────
    print("[3/11] Building market view...")
    market_view = market_regime_agent.build_layer5_market_view(
        market_signals=intelligence["market_signals"],
        memory_context=intelligence["memory_context"],
        run_id=run_id,
    )
    print(f"       regime={market_view.get('regime')} "
          f"posture={market_view.get('recommended_posture')} "
          f"risk={market_view.get('risk_level')}")

    # ── Step 4: Event impact classification ───────────────────────────────────
    print("[4/11] Classifying event impacts...")
    event_impact_views = event_impact_classifier.classify_all(
        events=intelligence["events"],
        entity_memory_map=intelligence["entity_memory_map"],
        theme_memory_map=intelligence["theme_memory_map"],
    )
    deep_dive_count = sum(1 for v in event_impact_views if v.get("requires_deep_dive"))
    print(f"       {len(event_impact_views)} event views | {deep_dive_count} require deep dive")

    # ── Step 5: Sector/theme intelligence ─────────────────────────────────────
    print("[5/11] Analyzing sector/theme intelligence...")
    sector_theme_views = sector_theme_agent.analyze_all(
        signal_groups=signal_groups,
        entities=intelligence["entities"],
        market_view=market_view,
    )
    high_str  = sum(1 for v in sector_theme_views if v.get("current_signal_strength") == "high")
    high_inv  = sum(1 for v in sector_theme_views if v.get("investment_relevance") == "high")
    print(f"       {len(sector_theme_views)} theme views | {high_str} high-signal | {high_inv} high-invest-relevance")

    # ── Step 6: Opportunity hypothesis generation (LLM) ──────────────────────
    print("[6/11] Generating opportunity hypotheses (LLM)...")
    llm = make_llm(provider=provider, temperature=0.1)
    opportunity_hypotheses = opportunity_hypothesis_generator.generate_all(
        signal_groups=signal_groups,
        sector_theme_views=sector_theme_views,
        event_impact_views=event_impact_views,
        market_view=market_view,
        llm=llm,
    )
    print(f"       {len(opportunity_hypotheses)} hypotheses generated")

    # ── Step 7: Cross-domain mapping (deferred) ───────────────────────────────
    print("[7/11] Cross-domain mapping (deferred)...")
    cross_domain_chains = cross_domain_mapper.map_cross_domain(
        opportunity_hypotheses=opportunity_hypotheses,
        theme_views=sector_theme_views,
        event_impact_views=event_impact_views,
        memory_context=intelligence["memory_context"],
    )
    print(f"       {len(cross_domain_chains)} cross-domain chains")

    # ── Step 8: Time horizon classification ───────────────────────────────────
    print("[8/11] Classifying time horizons...")
    time_horizon_views = time_horizon_classifier.classify_all(
        hypotheses=opportunity_hypotheses,
        signal_groups=signal_groups,
    )
    print(f"       {len(time_horizon_views)} time horizon views")

    # ── Step 9: Hypothesis strength scoring ───────────────────────────────────
    print("[9/11] Scoring hypothesis strength...")
    strength_scores = hypothesis_strength_scorer.score_all(
        hypotheses=opportunity_hypotheses,
        signal_groups=signal_groups,
        sector_theme_views=sector_theme_views,
        event_impact_views=event_impact_views,
        market_view=market_view,
    )
    to_l6    = sum(1 for s in strength_scores if s.get("send_to_layer6"))
    rejected = len(strength_scores) - to_l6
    print(f"       {to_l6} → Layer 6 | {rejected} rejected (score < 45)")

    # ── Step 10: Guardrail precheck ───────────────────────────────────────────
    print("[10/11] Running guardrail precheck...")
    guardrail_results = layer5_guardrail_precheck.check_all(
        hypotheses=opportunity_hypotheses,
        cross_domain_chains=cross_domain_chains,
        strength_scores=strength_scores,
        signal_groups=signal_groups,
    )
    # Attach guardrail status to hypotheses in-place
    opportunity_hypotheses = layer5_guardrail_precheck.apply_guardrail_decisions(
        hypotheses=opportunity_hypotheses,
        guardrail_results=guardrail_results,
    )
    gr_pass = sum(1 for r in guardrail_results if r.get("status") == "pass")
    gr_flag = len(guardrail_results) - gr_pass
    print(f"       {gr_pass} pass | {gr_flag} flagged/downgraded/quarantined")

    # ── Step 11: Write bundle ─────────────────────────────────────────────────
    print("[11/11] Writing Layer 5 outputs...")
    manifest = market_opportunity_bundle_builder.build_and_write(
        layer5_dir=layer5_dir,
        run_id=run_id,
        market_view=market_view,
        sector_theme_views=sector_theme_views,
        event_impact_views=event_impact_views,
        opportunity_hypotheses=opportunity_hypotheses,
        cross_domain_chains=cross_domain_chains,
        time_horizon_views=time_horizon_views,
        hypothesis_strength_scores=strength_scores,
        guardrail_results=guardrail_results,
        signal_groups=signal_groups,
        load_summary=intelligence["load_summary"],
    )
    print(f"\n{'='*60}")
    print(f"Layer 5 complete.")
    print(f"  Signal groups      : {len(signal_groups)}")
    print(f"  Event impact views : {len(event_impact_views)}")
    print(f"  Theme views        : {len(sector_theme_views)}")
    print(f"  Hypotheses         : {len(opportunity_hypotheses)}")
    print(f"  → Layer 6          : {to_l6}")
    print(f"  Output dir         : {layer5_dir}")
    print(f"{'='*60}\n")

    return manifest


def _build_run_id(target_date: str) -> str:
    now = datetime.now(_IST).strftime("%H%M")
    return f"RUN_{target_date.replace('-', '_')}_AUTONOMOUS_DAILY_{now}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 5 — Market & Opportunity Intelligence")
    parser.add_argument("--date",     default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--provider", default="gemini",
                        choices=["gemini", "openai", "lmstudio"],
                        help="LLM provider for hypothesis generation.")
    args = parser.parse_args()

    target_date = args.date
    base_out    = Path(__file__).parent.parent.parent / "output" / target_date

    layer3_dir = base_out / "layer3"
    layer4_dir = base_out / "layer4"
    layer5_dir = base_out / "layer5"

    if not layer3_dir.exists():
        print(f"ERROR: Layer 3 output not found at {layer3_dir}", file=sys.stderr)
        sys.exit(1)
    if not layer4_dir.exists():
        print(f"ERROR: Layer 4 output not found at {layer4_dir}", file=sys.stderr)
        sys.exit(1)

    run_id = _build_run_id(target_date)
    run(layer3_dir, layer4_dir, layer5_dir, run_id, provider=args.provider)


if __name__ == "__main__":
    main()
