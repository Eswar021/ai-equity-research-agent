---
name: Layer 7 Targeted Deep-Dive Extraction built
description: Layer 7 fully implemented; 13 modules in targeted_deep_dive/; 7 targets → 42 tasks → target_raw_bundles.json for L2
type: project
---
Layer 7 (Targeted Deep-Dive Extraction) is fully implemented and verified end-to-end as of 2026-05-11.

**Why:** Executes the deep_dive_plan.json from Layer 6 — runs Phase C collectors for each selected target and produces target_raw_bundles.json for Layer 2 canonicalization.

**How to apply:** Runs after Layer 6.
`python intelligence_layer/targeted_deep_dive/layer7_runner.py --date YYYY-MM-DD`

**13 modules in `intelligence_layer/targeted_deep_dive/`:**
- `deep_dive_plan_loader.py` — loads + sanity-checks L6 deep_dive_plan.json
- `target_execution_context_builder.py` — per-target context: output_dir, slug, metadata
- `collector_registry_adapter.py` — maps module name → Phase C fetch_* function + param builder (lazy import)
- `target_task_expander.py` — expands plan task specs into executable tasks with resolved output paths
- `target_task_scheduler.py` — ThreadPoolExecutor(max_workers=4) within each target; targets sequential
- `target_output_writer.py` — calls fetch fn, attaches traceability fields (_target_id, _module), writes JSON
- `target_extraction_status_tracker.py` — rolls up task results into per-target status (success/partial/failed)
- `target_source_record_builder.py` — creates TSRCREC_* records for L2 lineage
- `coverage_validator.py` — keyword-maps L6 questions → modules, flags gaps
- `missing_data_reporter.py` — explicit gap records for failed/skipped tasks
- `target_raw_bundle_builder.py` — assembles per-target bundle.json + full target_raw_bundles.json
- `post_collection_router.py` — writes all artifacts + L2 handoff manifest
- `layer7_runner.py` — 7-step orchestrator

**Key design decisions (see docs/architecture_decisions/decisions.md):**
- Calls `fetch_*` not `save_*` — Layer 7 controls output path (ADR-L7-003)
- screener_in URL derived from ticker (ADR-L7-004)
- Sequential targets, parallel tasks per target (ADR-L7-005)
- parameter_validator, audit_logger not built (ADR-L7-001, L7-002)
- Non-listed collectors not built — nothing selected of those types (ADR-L7-006)

**Scale (2026-05-10 run):** 7 targets × 6 modules = 42 tasks
- market_data: 1 snapshot per target
- price_history: 249 daily bars (1y)
- screener_in: 12 quarters
- peer_comparison: 9-15 peers
- analyst_estimates: 4 recommendation periods
- exchange_filings: 50 announcements

**Output dir files:** target_raw_bundles.json, target_source_records.json (42 records), target_extraction_status.json, coverage_report.json (0.86 completeness), missing_data_report.json, layer7_manifest.json, targets/{TARGET_ID}_{SLUG}/ (7 dirs with 7 JSON files each)

**Layer 7 → Layer 2 contract:** `layer7_manifest.json[next_layer_input]` has `raw_bundle_path`, `source_records_path`, `collection_status_path` for L2 canonicalization

**Architecture decision log:** `docs/architecture_decisions/decisions.md` — tracks all deviations from design docs across L6 + L7
