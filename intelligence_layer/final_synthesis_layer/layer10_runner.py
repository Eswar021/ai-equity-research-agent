"""
intelligence_layer/final_synthesis_layer/layer10_runner.py — Layer 10

Portfolio Intelligence + Final Report controller.

Reads L9 specialist scorecards (and L8, L5, L6 supporting context),
synthesizes final target views, ranks opportunities, applies recommendation
policy, builds scenarios, writes the daily investor report.

Pipeline (12 steps):
  1. Load inputs (L9 + L8 + L5 + L6)
  2. Assemble per-target synthesis contexts
  3. Synthesize market posture
  4. Run target synthesis (LLM × N targets)
  5. Rank opportunities
  6. Apply recommendation policy
  7. Calibrate confidence
  8. Build scenarios (LLM × N targets)
  9. Build watchlist actions
  10. Build memory update instructions
  11. Write final report (Markdown + JSON)
  12. Run guardrails + write all artifacts + manifest

Run standalone:
    python intelligence_layer/final_synthesis_layer/layer10_runner.py
    python intelligence_layer/final_synthesis_layer/layer10_runner.py --date 2026-05-10
    python intelligence_layer/final_synthesis_layer/layer10_runner.py --provider openai --model gpt-4.1-mini

ADR-L10-001: LLM for narrative only; scoring/policy deterministic.
ADR-L10-002: method="function_calling" on all LLM agents.
ADR-L10-003: scenarios fallback gracefully on LLM error.
ADR-L10-004: portfolio_context_analyzer deferred (no portfolio in v1 test run).
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.paths import LAYER5_DIR, LAYER6_DIR, LAYER8_DIR, LAYER9_DIR, LAYER10_DIR
from llm.llm_client import make_llm

from intelligence_layer.final_synthesis_layer import (
    final_input_loader,
    final_context_assembler,
    market_posture_synthesizer,
    target_synthesis_engine,
    opportunity_ranker,
    recommendation_policy_engine,
    risk_confidence_calibrator,
    scenario_and_invalidation_builder,
    watchlist_action_builder,
    memory_update_instruction_builder,
    final_report_writer,
    final_guardrail_validator,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(
    layer9_dir: Path,
    layer8_dir: Path,
    layer5_dir: Path,
    layer6_dir: Path,
    layer10_dir: Path,
    provider: str = "openai",
    model: str | None = None,
) -> dict:
    layer9_dir  = Path(layer9_dir)
    layer8_dir  = Path(layer8_dir)
    layer5_dir  = Path(layer5_dir)
    layer6_dir  = Path(layer6_dir)
    layer10_dir = Path(layer10_dir)
    layer10_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"Layer 10 — Portfolio Intelligence + Final Report")
    print(f"L9 dir   : {layer9_dir}")
    print(f"L10 dir  : {layer10_dir}")
    print(f"Provider : {provider}")
    if model:
        print(f"Model    : {model}")
    print(f"{'='*60}\n")

    # ── Step 1: Load inputs ───────────────────────────────────────────────────
    print("[1/12] Loading inputs (L9 + L8 + L5 + L6)...")
    inputs = final_input_loader.load(layer9_dir, layer8_dir, layer5_dir, layer6_dir)
    scorecards  = inputs.get("target_scorecards", [])
    run_id      = inputs.get("research_run_id", f"RUN_{today.replace('-','')}")
    print(f"        scorecards={len(scorecards)}"
          f"  assessments={len(inputs.get('specialist_assessments',[]))}"
          f"  evidence_cards={len(inputs.get('evidence_cards',[]))}"
          f"  hypotheses={len(inputs.get('opportunity_hypotheses',[]))}")

    if not scorecards:
        print("ERROR: No target scorecards found. Did Layer 9 run successfully?", file=sys.stderr)
        sys.exit(1)

    ready = [sc for sc in scorecards if sc.get("ready_for_layer10")]
    print(f"        {len(ready)}/{len(scorecards)} targets ready for L10")

    # ── Step 2: Assemble target contexts ──────────────────────────────────────
    print("\n[2/12] Assembling target synthesis contexts...")
    target_contexts = final_context_assembler.build_all(inputs)
    ctx_by_tid = {c["target_id"]: c for c in target_contexts}
    print(f"        {len(target_contexts)} contexts assembled")

    # ── Step 3: Market posture ────────────────────────────────────────────────
    print("\n[3/12] Synthesizing market posture...")
    market_posture = market_posture_synthesizer.synthesize(inputs.get("market_view", {}))
    print(f"        posture={market_posture['final_market_posture']}"
          f"  risk={market_posture['risk_level']}"
          f"  regime={market_posture['regime']}")

    # ── Step 4: Target synthesis (LLM) ───────────────────────────────────────
    print(f"\n[4/12] Running target synthesis ({provider}, {len(target_contexts)} LLM calls)...")
    llm_kwargs: dict = {"provider": provider}
    if model:
        llm_kwargs["model"] = model
    llm = make_llm(**llm_kwargs)

    target_syntheses: list[dict] = []
    for i, ctx in enumerate(target_contexts):
        name = ctx.get("target_name", ctx["target_id"])
        print(f"        [{i+1}/{len(target_contexts)}] synthesizing {name}...", end=" ", flush=True)
        try:
            syn = target_synthesis_engine.synthesize(ctx, market_posture, llm)
            target_syntheses.append(syn)
            print(f"done (conf={syn.get('synthesis_confidence','?')})")
        except Exception as e:
            print(f"FAILED: {e}")
            # Fallback synthesis from scorecard data
            sc = ctx["scorecard"]
            target_syntheses.append(_fallback_synthesis(ctx, sc))

    print(f"        {len(target_syntheses)} target syntheses complete")

    # ── Step 5: Rank opportunities ────────────────────────────────────────────
    print("\n[5/12] Ranking opportunities...")
    ranked = opportunity_ranker.rank_all(target_syntheses, target_contexts, market_posture)
    for r in ranked:
        print(f"        #{r['rank']} {r['target_name'][:35]:35} score={r['final_opportunity_score']:.0f}")

    # ── Step 6: Recommendation policy ────────────────────────────────────────
    print("\n[6/12] Applying recommendation policy...")
    policy_results = recommendation_policy_engine.apply_all(ranked, ctx_by_tid)
    for r in policy_results:
        print(f"        {r['target_name'][:30]:30} → {r['action_label']:25}  overrides={r['policy_overrides']}")

    # ── Step 7: Calibrate confidence ──────────────────────────────────────────
    print("\n[7/12] Calibrating confidence...")
    calibrated = risk_confidence_calibrator.calibrate_all(policy_results, ctx_by_tid)
    for r in calibrated:
        ic = r.get("initial_confidence", "?")
        fc = r.get("final_confidence", "?")
        label = r.get("confidence_label", "?")
        if isinstance(ic, float) and isinstance(fc, float) and abs(fc - ic) > 0.01:
            print(f"        {r['target_name'][:30]:30}  {ic:.3f} → {fc:.3f} ({label})")

    # ── Step 8: Scenarios (LLM) ───────────────────────────────────────────────
    print(f"\n[8/12] Building scenarios ({len(calibrated)} LLM calls)...")
    with_scenarios = scenario_and_invalidation_builder.build_all(calibrated, ctx_by_tid, llm)
    for r in with_scenarios:
        has = "ok" if r.get("scenario_analysis", {}).get("bull_case") else "fallback"
        print(f"        {r['target_name'][:35]:35}  [{has}]")

    # ── Step 9: Watchlist actions ─────────────────────────────────────────────
    print("\n[9/12] Building watchlist actions...")
    watchlist_actions = watchlist_action_builder.build_all(with_scenarios, today)
    print(f"        {len(watchlist_actions)} actions built")

    # ── Step 10: Memory update instructions ───────────────────────────────────
    print("\n[10/12] Building memory update instructions...")
    mem_instructions = memory_update_instruction_builder.build_all(with_scenarios, run_id, today)
    print(f"        {len(mem_instructions)} instructions built")

    # ── Step 11: Write report ─────────────────────────────────────────────────
    print("\n[11/12] Writing final report...")
    md_path, report_json = final_report_writer.write_report(
        final_cards       = with_scenarios,
        market_summary    = market_posture,
        watchlist_actions = watchlist_actions,
        research_run_id   = run_id,
        date_str          = today,
        layer10_dir       = layer10_dir,
    )
    print(f"        Markdown → {Path(md_path).name}")
    print(f"        JSON     → {Path(md_path).stem}.json")

    # ── Step 12: Guardrails + write artifacts + manifest ──────────────────────
    print("\n[12/12] Running guardrails and writing artifacts...")
    guardrail_report = final_guardrail_validator.validate(with_scenarios)
    print(f"        guardrail status={guardrail_report['status']}"
          f"  issues={guardrail_report['issues_count']}"
          f"  warnings={guardrail_report['warnings_count']}")
    if guardrail_report.get("issues"):
        for issue in guardrail_report["issues"][:3]:
            print(f"        [ISSUE] {issue.get('message','')[:100]}")

    # Write all artifacts
    _write(layer10_dir / "target_recommendation_cards.json", with_scenarios)
    _write(layer10_dir / "watchlist_actions.json",            watchlist_actions)
    _write(layer10_dir / "memory_update_instructions.json",   mem_instructions)
    _write(layer10_dir / "final_guardrail_report.json",       guardrail_report)
    _write(layer10_dir / "market_summary_card.json",          market_posture)

    # Summary counts
    rc_count = sum(1 for c in with_scenarios if c.get("action_label") == "research_candidate")
    wl_count = sum(1 for c in with_scenarios if c.get("action_label") in ("watchlist", "wait_for_confirmation"))
    av_count = sum(1 for c in with_scenarios if c.get("action_label") in ("avoid_for_now", "too_speculative"))

    manifest = {
        "research_run_id":    run_id,
        "layer":              "L10_portfolio_intelligence_final_report",
        "created_at":         datetime.now(_IST).isoformat(),
        "provider":           provider,
        "model":              model,
        "date":               today,
        "targets_synthesized": len(with_scenarios),
        "counts": {
            "research_candidates":    rc_count,
            "watchlist":              wl_count,
            "avoid_or_speculative":   av_count,
            "watchlist_actions":      len(watchlist_actions),
            "memory_instructions":    len(mem_instructions),
            "guardrail_issues":       guardrail_report["issues_count"],
        },
        "artifacts": {
            "final_daily_report_md":            md_path,
            "final_daily_report_json":          str(layer10_dir / f"final_daily_report_{today}.json"),
            "target_recommendation_cards":      str(layer10_dir / "target_recommendation_cards.json"),
            "watchlist_actions":                str(layer10_dir / "watchlist_actions.json"),
            "memory_update_instructions":       str(layer10_dir / "memory_update_instructions.json"),
            "market_summary_card":              str(layer10_dir / "market_summary_card.json"),
            "final_guardrail_report":           str(layer10_dir / "final_guardrail_report.json"),
        },
    }
    _write(layer10_dir / "layer10_manifest.json", manifest)

    print(f"\n{'='*60}")
    print(f"Layer 10 complete.")
    print(f"  Targets synthesized   : {len(with_scenarios)}")
    print(f"  Research candidates   : {rc_count}")
    print(f"  Watchlist             : {wl_count}")
    print(f"  Avoid / speculative   : {av_count}")
    print(f"  Watchlist actions     : {len(watchlist_actions)}")
    print(f"  Memory instructions   : {len(mem_instructions)}")
    print(f"  Guardrail             : {guardrail_report['status']}")
    print(f"  Output dir            : {layer10_dir}")
    print(f"{'='*60}\n")

    return manifest


def _fallback_synthesis(ctx: dict, sc: dict) -> dict:
    dim = sc.get("dimension_scores", {})
    return {
        "target_id":             ctx["target_id"],
        "target_name":           ctx["target_name"],
        "ticker":                ctx["ticker"],
        "target_type":           ctx.get("target_type", "listed_company"),
        "time_horizon":          sc.get("time_horizon", ""),
        "thesis_status":         sc.get("thesis_status", ""),
        "final_view_rationale":  "LLM synthesis unavailable; scorecard metrics used.",
        "final_summary":         sc.get("thesis_statement_snippet", "")[:300],
        "supporting_points":     sc.get("top_supportive_points", [])[:3],
        "weakening_points":      [r[:100] for r in sc.get("top_risks", [])[:2]],
        "critical_gaps_summary": sc.get("critical_data_gaps", [])[:3],
        "specialist_alignment":  f"thesis={sc.get('thesis_status','?')}",
        "dimension_scores":      dim,
        "dimension_labels":      sc.get("dimension_labels", {}),
        "overall_specialist_confidence": sc.get("overall_specialist_confidence", 0.5),
        "synthesis_confidence":  sc.get("overall_specialist_confidence", 0.5),
        "not_final_recommendation": True,
    }


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    size = len(data) if isinstance(data, (list, dict)) else "?"
    print(f"        wrote {path.name}  ({size} items)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 10 — Portfolio Intelligence + Final Report")
    parser.add_argument("--date",     default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--provider", default="openai",
                        help="LLM provider: openai | gemini | lmstudio")
    parser.add_argument("--model",    default=None,
                        help="Override model name.")
    args = parser.parse_args()

    base_out    = Path(__file__).parent.parent.parent / "output" / args.date
    layer9_dir  = base_out / "layer9"
    layer8_dir  = base_out / "layer8"
    layer5_dir  = base_out / "layer5"
    layer6_dir  = base_out / "layer6"
    layer10_dir = base_out / "layer10"

    if not (layer9_dir / "target_specialist_scorecards.json").exists():
        print(f"ERROR: target_specialist_scorecards.json not found at {layer9_dir}", file=sys.stderr)
        print(f"       Run Layer 9 first.", file=sys.stderr)
        sys.exit(1)

    run(layer9_dir, layer8_dir, layer5_dir, layer6_dir, layer10_dir,
        provider=args.provider, model=args.model)


if __name__ == "__main__":
    main()
