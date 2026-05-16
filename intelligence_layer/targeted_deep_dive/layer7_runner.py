"""
intelligence_layer/targeted_deep_dive/layer7_runner.py — Layer 7

Main controller for Targeted Deep-Dive Extraction.
Reads deep_dive_plan.json from Layer 6, executes all collector tasks,
writes target_raw_bundles.json + supporting artifacts for Layer 2.

Pipeline (7 steps):
  1. Load deep_dive_plan.json
  2. Build execution contexts per target
  3. For each target: expand tasks → run collectors (parallel within target)
  4. Build extraction status per target
  5. Build source records + coverage + missing data reports
  6. Assemble target_raw_bundles.json
  7. Write all artifacts + Layer 2 handoff manifest

Run standalone:
    python intelligence_layer/targeted_deep_dive/layer7_runner.py
    python intelligence_layer/targeted_deep_dive/layer7_runner.py --date 2026-05-10

Design doc: docs/system_design_docs/layer_7.md §10.1 layer7_runner.py
"""

from __future__ import annotations
import argparse
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.paths import LAYER6_DIR, LAYER7_DIR

from intelligence_layer.targeted_deep_dive import (
    deep_dive_plan_loader,
    target_execution_context_builder,
    target_task_expander,
    target_task_scheduler,
    target_extraction_status_tracker,
    target_source_record_builder,
    coverage_validator,
    missing_data_reporter,
    target_raw_bundle_builder,
    post_collection_router,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer6_dir: Path, layer7_dir: Path) -> dict:
    """Execute the full Layer 7 pipeline. Returns manifest dict."""
    layer6_dir = Path(layer6_dir)
    layer7_dir = Path(layer7_dir)

    print(f"\n{'='*60}")
    print(f"Layer 7 — Targeted Deep-Dive Extraction")
    print(f"L6 dir  : {layer6_dir}")
    print(f"L7 dir  : {layer7_dir}")
    print(f"{'='*60}\n")

    # ── Step 1: Load deep_dive_plan ───────────────────────────────────────────
    print("[1/7] Loading deep_dive_plan.json...")
    plan_result  = deep_dive_plan_loader.load(layer6_dir / "deep_dive_plan.json")
    plan         = plan_result["plan"]
    load_summary = plan_result["load_summary"]
    plan_id      = load_summary["plan_id"]
    research_run_id = plan.get("research_run_id", "")
    print(f"       plan_id={plan_id} targets={load_summary['target_count']} tasks={load_summary['task_count']}")
    if load_summary["warnings"]:
        for w in load_summary["warnings"]:
            print(f"       WARN: {w}")

    # ── Step 2: Build execution contexts ─────────────────────────────────────
    print("[2/7] Building target execution contexts...")
    contexts = target_execution_context_builder.build_all_contexts(plan, layer7_dir)
    print(f"       {len(contexts)} contexts built")
    for ctx in contexts:
        print(f"       {ctx['target_id']} | {ctx['target_name'][:35]:35} | {ctx['ticker']}")

    # ── Step 3: Expand + execute tasks per target ─────────────────────────────
    print("[3/7] Executing collector tasks...")
    all_task_results: dict[str, list[dict]] = {}
    all_skipped:      dict[str, list[dict]] = {}

    for ctx in contexts:
        tasks, skipped = target_task_expander.expand(ctx)
        all_skipped[ctx["target_id"]] = skipped
        print(f"\n  {ctx['target_name']} ({ctx['ticker']}): {len(tasks)} tasks, {len(skipped)} skipped")

        results = target_task_scheduler.run_tasks(tasks, max_workers=4)
        all_task_results[ctx["target_id"]] = results

        for r in results:
            status_icon = "✓" if r["status"] == "success" else "✗"
            print(f"    {status_icon} {r['module']:20} records={r['record_count']:4}  {r['error'] or ''}")

    # ── Step 4: Build extraction statuses ─────────────────────────────────────
    print("\n[4/7] Building extraction statuses...")
    statuses = target_extraction_status_tracker.build_all_statuses(
        contexts, all_task_results, all_skipped
    )
    success_count  = sum(1 for s in statuses if s["target_status"] == "success")
    partial_count  = sum(1 for s in statuses if s["target_status"] == "partial_success")
    failed_count   = sum(1 for s in statuses if s["target_status"] == "failed")
    print(f"       success={success_count} partial={partial_count} failed={failed_count}")

    # ── Step 5: Source records + coverage + missing data ──────────────────────
    print("[5/7] Building source records, coverage + missing data reports...")
    source_records = target_source_record_builder.build_all_source_records(
        contexts, all_task_results, plan_id, research_run_id
    )
    coverage_list = coverage_validator.validate_all_coverage(contexts, all_task_results)
    missing_data  = missing_data_reporter.report_all_missing(
        contexts, all_task_results, all_skipped
    )
    print(f"       source_records={len(source_records)} missing_items={len(missing_data)}")

    # Coverage indexed by target_id for bundle builder
    coverage_by_target = {c["target_id"]: c for c in coverage_list}
    missing_by_target  = {}
    for m in missing_data:
        missing_by_target.setdefault(m["target_id"], []).append(m)

    # ── Step 6: Assemble target_raw_bundles.json ──────────────────────────────
    print("[6/7] Assembling target_raw_bundles.json...")
    bundle_summary = target_raw_bundle_builder.build_and_write(
        layer7_dir=layer7_dir,
        research_run_id=research_run_id,
        contexts=contexts,
        all_task_results=all_task_results,
        all_skipped=all_skipped,
        coverage_by_target=coverage_by_target,
        missing_by_target=missing_by_target,
    )
    print(f"       {bundle_summary['total_targets']} target bundles written")

    # ── Step 7: Write all artifacts + Layer 2 manifest ───────────────────────
    print("[7/7] Writing artifacts + Layer 2 handoff manifest...")
    manifest = post_collection_router.write_and_route(
        layer7_dir=layer7_dir,
        research_run_id=research_run_id,
        plan_id=plan_id,
        extraction_statuses=statuses,
        source_records=source_records,
        coverage_list=coverage_list,
        missing_data=missing_data,
        bundle_summary=bundle_summary,
    )

    total_tasks_run = manifest["collector_tasks_run"]
    tasks_ok        = manifest["collector_tasks_success"]
    tasks_fail      = manifest["collector_tasks_failed"]

    print(f"\n{'='*60}")
    print(f"Layer 7 complete.")
    print(f"  Targets processed  : {len(contexts)}")
    print(f"  Targets success    : {success_count}")
    print(f"  Targets partial    : {partial_count}")
    print(f"  Tasks run          : {total_tasks_run}")
    print(f"  Tasks success      : {tasks_ok}")
    print(f"  Tasks failed       : {tasks_fail}")
    print(f"  Source records     : {len(source_records)}")
    print(f"  Missing data items : {len(missing_data)}")
    print(f"  Output dir         : {layer7_dir}")
    print(f"{'='*60}\n")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 7 — Targeted Deep-Dive Extraction")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target_date = args.date
    base_out    = Path(__file__).parent.parent.parent / "output" / target_date
    layer6_dir  = base_out / "layer6"
    layer7_dir  = base_out / "layer7"

    if not (layer6_dir / "deep_dive_plan.json").exists():
        print(f"ERROR: deep_dive_plan.json not found at {layer6_dir}", file=sys.stderr)
        sys.exit(1)

    run(layer6_dir, layer7_dir)


if __name__ == "__main__":
    main()
