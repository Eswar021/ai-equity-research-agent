"""
intelligence_layer/specialist_analysis/layer9_runner.py — Layer 9

Specialist Analysis Agents controller.

Reads L8 agent_context_packets and evidence, runs 4 specialist LLM agents
(fundamental, valuation, risk, thesis_validation), calibrates confidence,
detects cross-agent disagreements, and builds per-target scorecards.

Pipeline (8 steps):
  1. Load L8 inputs
  2. Plan agent tasks (thesis always last)
  3. Run all agents via orchestrator
  4. Calibrate confidence (post-hoc, rule-based)
  5. Build consolidated risk flags
  6. Detect cross-agent disagreements
  7. Build target specialist scorecards
  8. Write artifacts + L10 manifest

Run standalone:
    python intelligence_layer/specialist_analysis/layer9_runner.py
    python intelligence_layer/specialist_analysis/layer9_runner.py --date 2026-05-10
    python intelligence_layer/specialist_analysis/layer9_runner.py --provider openai
    python intelligence_layer/specialist_analysis/layer9_runner.py --provider openai --model gpt-4.1-mini

ADR-L9-001: thesis_agent runs last; receives prior_assessments from other 3 agents
ADR-L9-002: inline guardrails in orchestrator — no dedicated guardrail module
ADR-L9-003: 4 agent types matching L8's 4 packet types
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.paths import LAYER8_DIR, LAYER9_DIR
from llm.llm_client import make_llm

from intelligence_layer.specialist_analysis import (
    agent_input_loader,
    agent_task_planner,
    agent_execution_orchestrator,
    confidence_calibrator,
    risk_flag_builder,
    agent_disagreement_detector,
    target_specialist_scorecard_builder,
    agent_quality_reporter,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer8_dir: Path, layer9_dir: Path, provider: str = "openai", model: str | None = None) -> dict:
    layer8_dir = Path(layer8_dir)
    layer9_dir = Path(layer9_dir)
    layer9_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y-%m-%d").replace("-", "")

    print(f"\n{'='*60}")
    print(f"Layer 9 — Specialist Analysis Agents")
    print(f"L8 dir   : {layer8_dir}")
    print(f"L9 dir   : {layer9_dir}")
    print(f"Provider : {provider}")
    if model:
        print(f"Model    : {model}")
    print(f"{'='*60}\n")

    # ── Step 1: Load L8 inputs ─────────────────────────────────────────────────
    print("[1/8] Loading L8 inputs...")
    inputs = agent_input_loader.load(layer8_dir)
    research_run_id = inputs.get("research_run_id", f"RUN_{today}")
    packets_by_target = inputs.get("packets_by_target", {})
    print(f"       targets={len(packets_by_target)} packets loaded")
    for tid, agent_packets in packets_by_target.items():
        name = next(
            (p.get("target_summary", {}).get("target_name", "") for p in agent_packets.values()
             if isinstance(p, dict)),
            ""
        )
        print(f"       {tid} | {name[:40]:40} | agent_types={list(agent_packets.keys())}")

    if not packets_by_target:
        print("ERROR: No agent packets found. Did Layer 8 run successfully?", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Plan tasks ─────────────────────────────────────────────────────
    print("\n[2/8] Planning agent tasks...")
    tasks = agent_task_planner.plan_tasks(inputs)
    print(f"       {len(tasks)} tasks planned")
    for t in tasks:
        print(f"       [{t['priority']:6}] {t['agent_type']:25} target={t['target_id']}")

    # ── Step 3: Run all agents ─────────────────────────────────────────────────
    print(f"\n[3/8] Running specialist agents ({provider})...")
    llm_kwargs: dict = {"provider": provider}
    if model:
        llm_kwargs["model"] = model
    llm = make_llm(**llm_kwargs)

    task_results = agent_execution_orchestrator.run_all_tasks(tasks, inputs, llm)

    succeeded = sum(1 for r in task_results if r["status"] == "success")
    failed    = sum(1 for r in task_results if r["status"] == "failed")
    print(f"       done — succeeded={succeeded} failed={failed}")
    for r in task_results:
        assess = r.get("assessment", {})
        status = r["status"]
        label  = assess.get("assessment_label", "") if status in ("success", "partial") else (r.get("error") or "")[:60]
        conf   = f"  conf={assess.get('confidence', '?')}" if status in ("success", "partial") else ""
        print(f"       [{status:7}] {r['agent_type']:25} {r['target_id']}  {label}{conf}")

    # ── Step 4: Calibrate confidence ──────────────────────────────────────────
    print("\n[4/8] Calibrating confidence...")
    task_results = confidence_calibrator.calibrate_all(task_results, inputs)
    for r in task_results:
        if r["status"] == "success":
            a = r["assessment"]
            orig = a.get("original_confidence", "?")
            cal  = a.get("confidence", "?")
            reasons = a.get("calibration_reasons", [])
            if reasons and reasons[0] != "No calibration adjustments needed":
                print(f"       {r['agent_type']:25} {r['target_id']}  {orig} → {cal}  ({reasons[0]})")

    # ── Step 5: Build risk flags ───────────────────────────────────────────────
    print("\n[5/8] Consolidating risk flags...")
    risk_flags = risk_flag_builder.build_all(task_results, inputs, today)
    print(f"       {len(risk_flags)} risk flags consolidated")

    # ── Step 6: Detect disagreements ──────────────────────────────────────────
    print("\n[6/8] Detecting agent disagreements...")
    disagreements = agent_disagreement_detector.detect_all(task_results, today)
    print(f"       {len(disagreements)} disagreements detected")
    for d in disagreements:
        print(f"       [{d['severity']:6}] {d['disagreement_type']}  target={d['target_id']}")

    # ── Step 7: Build scorecards ───────────────────────────────────────────────
    print("\n[7/8] Building target specialist scorecards...")
    scorecards = target_specialist_scorecard_builder.build_all(
        task_results, risk_flags, disagreements, inputs, today
    )
    print(f"       {len(scorecards)} scorecards built")
    ready_count = sum(1 for s in scorecards if s.get("ready_for_layer10"))
    for sc in scorecards:
        ready = "READY" if sc.get("ready_for_layer10") else "NOT_READY"
        thesis = sc.get("thesis_status", "")
        conf   = sc.get("overall_specialist_confidence", 0)
        print(f"       [{ready:9}] {sc['target_id']}  thesis={thesis:25}  conf={conf:.3f}")

    # ── Step 8: Write artifacts ────────────────────────────────────────────────
    print("\n[8/8] Writing artifacts...")

    _write(layer9_dir / "specialist_assessments.json",    task_results)
    _write(layer9_dir / "risk_flags.json",                risk_flags)
    _write(layer9_dir / "agent_disagreements.json",       disagreements)
    _write(layer9_dir / "target_specialist_scorecards.json", scorecards)

    quality_report = agent_quality_reporter.build_report(
        research_run_id=research_run_id,
        task_results=task_results,
        risk_flags=risk_flags,
        disagreements=disagreements,
        scorecards=scorecards,
        date_str=today,
    )
    _write(layer9_dir / "agent_quality_report.json", quality_report)

    manifest = {
        "research_run_id":   research_run_id,
        "layer":             "L9_specialist_analysis",
        "created_at":        datetime.now(_IST).isoformat(),
        "provider":          provider,
        "model":             model,
        "targets_processed": len(scorecards),
        "targets_ready_for_layer10": ready_count,
        "artifacts": {
            "specialist_assessments":       str(layer9_dir / "specialist_assessments.json"),
            "risk_flags":                   str(layer9_dir / "risk_flags.json"),
            "agent_disagreements":          str(layer9_dir / "agent_disagreements.json"),
            "target_specialist_scorecards": str(layer9_dir / "target_specialist_scorecards.json"),
            "agent_quality_report":         str(layer9_dir / "agent_quality_report.json"),
        },
        "counts": {
            "agent_tasks_total":   len(task_results),
            "agent_tasks_success": succeeded,
            "agent_tasks_failed":  failed,
            "risk_flags":          len(risk_flags),
            "disagreements":       len(disagreements),
            "scorecards":          len(scorecards),
        },
        "next_layer_input": {
            "target_specialist_scorecards_path": str(layer9_dir / "target_specialist_scorecards.json"),
            "specialist_assessments_path":       str(layer9_dir / "specialist_assessments.json"),
            "risk_flags_path":                   str(layer9_dir / "risk_flags.json"),
            "agent_disagreements_path":           str(layer9_dir / "agent_disagreements.json"),
        },
    }
    _write(layer9_dir / "layer9_manifest.json", manifest)

    qr = quality_report
    print(f"\n{'='*60}")
    print(f"Layer 9 complete.")
    print(f"  Tasks total       : {qr['tasks_total']}")
    print(f"  Tasks succeeded   : {qr['tasks_succeeded']}")
    print(f"  Tasks failed      : {qr['tasks_failed']}")
    print(f"  Targets processed : {qr['targets_processed']}")
    print(f"  Ready for L10     : {qr['targets_ready_for_layer10']}")
    print(f"  Risk flags        : {qr['risk_flags_total']}")
    print(f"  Disagreements     : {qr['disagreements_total']}")
    print(f"  Output dir        : {layer9_dir}")
    print(f"{'='*60}\n")

    return manifest


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    size = len(data) if isinstance(data, list) else "obj"
    print(f"       wrote {path.name}  ({size} items)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 9 — Specialist Analysis Agents")
    parser.add_argument("--date",     default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--provider", default="openai",
                        help="LLM provider: openai | gemini | lmstudio")
    parser.add_argument("--model",    default=None,
                        help="Override model name for the provider.")
    args = parser.parse_args()

    base_out   = Path(__file__).parent.parent.parent / "output" / args.date
    layer8_dir = base_out / "layer8"
    layer9_dir = base_out / "layer9"

    if not (layer8_dir / "agent_context_packets.json").exists():
        print(f"ERROR: agent_context_packets.json not found at {layer8_dir}", file=sys.stderr)
        print(f"       Run Layer 8 first.", file=sys.stderr)
        sys.exit(1)

    run(layer8_dir, layer9_dir, provider=args.provider, model=args.model)


if __name__ == "__main__":
    main()
