"""
intelligence_layer/memory_qualification/layer4_runner.py — Layer 4

Main controller for the Memory Qualification + Knowledge Base layer.

Pipeline:
  1. Load Layer 3 intelligence objects
  2. Build memory candidates
  3. Load existing memory indexes + records
  4. For each candidate: score → check novelty → track recurrence → classify → decide
  5. Validate schema
  6. Write new records / update existing
  7. Handle thesis memory
  8. Apply memory decay
  9. Build memory context packet
  10. Write audit log + outputs

Run standalone:
    python intelligence_layer/memory_qualification/layer4_runner.py
    python intelligence_layer/memory_qualification/layer4_runner.py --date 2026-05-10

Design doc: docs/system_design_docs/layer_4.md §1 layer4_runner.py
"""

from __future__ import annotations
import json
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import (
    LAYER3_DIR, LAYER4_DIR,
    DB_MEMORY_DIR, DB_ENTITY_MEMORY_INDEX_FILE,
    DB_THEME_MEMORY_INDEX_FILE, DB_MEMORY_AUDIT_INDEX_FILE,
    DB_SHORT_TERM_MEMORY_FILE, DB_WATCH_MEMORY_FILE,
    DB_LONG_TERM_MEMORY_FILE, DB_THESIS_MEMORY_FILE,
)

from intelligence_layer.memory_qualification import (
    intelligence_input_loader,
    memory_candidate_builder,
    memory_relevance_scorer,
    novelty_checker,
    recurrence_tracker,
    memory_type_classifier,
    memory_qualification_agent,
    memory_schema_validator,
    memory_writer,
    memory_updater,
    thesis_memory_manager,
    memory_decay_manager,
    memory_retriever,
    memory_audit_logger,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer3_dir: Path | None = None,
        layer4_dir: Path | None = None,
        db_memory_dir: Path | None = None,
        run_id: str = "",
        min_memory_score: int = 35) -> dict:
    """
    Full Layer 4 run.

    Returns summary dict with paths to all output files.
    """
    l3_dir    = layer3_dir  or LAYER3_DIR
    l4_dir    = layer4_dir  or LAYER4_DIR
    db_dir    = db_memory_dir or DB_MEMORY_DIR

    l4_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)
    (db_dir / "working_memory").mkdir(parents=True, exist_ok=True)

    run_id = run_id or f"RUN_{date.today().strftime('%Y_%m_%d')}_LAYER4"

    print(f"\n{'='*60}")
    print(f"  Layer 4 — Memory Qualification")
    print(f"  Run:      {run_id}")
    print(f"  L3 input: {l3_dir}")
    print(f"  L4 out:   {l4_dir}")
    print(f"  DB:       {db_dir}")
    print(f"{'='*60}\n")

    # ── Step 1: Load Layer 3 outputs ──────────────────────────────────────────
    print("Step 1  Loading Layer 3 intelligence objects...")
    intelligence = intelligence_input_loader.load(l3_dir)
    _print_load_summary(intelligence["load_summary"])

    total_objects = sum(
        len(intelligence.get(k) or [])
        for k in ("events", "themes", "facts", "claims", "market_signals")
    )
    if total_objects == 0:
        print("  ✗  No intelligence objects found. Exiting.")
        return {"status": "no_input", "run_id": run_id}

    # ── Step 2: Build memory candidates ───────────────────────────────────────
    print("\nStep 2  Building memory candidates...")
    candidates = memory_candidate_builder.build_candidates(intelligence, run_id)
    print(f"  ✓  {len(candidates)} candidates from {total_objects} objects")

    # ── Step 3: Load existing memory indexes and all records ──────────────────
    print("\nStep 3  Loading existing memory indexes...")
    entity_index, theme_index = novelty_checker.load_index_files(
        DB_ENTITY_MEMORY_INDEX_FILE, DB_THEME_MEMORY_INDEX_FILE
    )
    print(f"  ✓  entity_index: {len(entity_index)} entities, theme_index: {len(theme_index)} themes")

    all_memory_files = [
        DB_SHORT_TERM_MEMORY_FILE,
        DB_WATCH_MEMORY_FILE,
        DB_LONG_TERM_MEMORY_FILE,
        DB_THESIS_MEMORY_FILE,
    ]
    all_records = recurrence_tracker.load_all_records(all_memory_files)
    print(f"  ✓  {len(all_records)} existing memory records loaded")

    # ── Steps 4–8: Per-candidate pipeline ────────────────────────────────────
    print(f"\nStep 4-8  Processing {len(candidates)} candidates...")

    decisions_out:   list[dict] = []
    new_records:     list[dict] = []
    update_logs:     list[dict] = []
    thesis_updates:  list[dict] = []
    audit_entries:   list[dict] = []
    quarantine:      list[dict] = []

    counters = {"stored": 0, "updated": 0, "ignored": 0,
                "quarantined": 0, "thesis": 0}

    audit_file = DB_MEMORY_AUDIT_INDEX_FILE

    for cand in candidates:
        # Score
        novelty_r  = novelty_checker.check(cand, entity_index, theme_index)
        recurrence_r = recurrence_tracker.track(cand, all_records)

        score_r = memory_relevance_scorer.score(
            cand,
            recurrence=recurrence_r,
            novelty_status=novelty_r["novelty_status"],
        )

        # Classify
        classification = memory_type_classifier.classify(
            cand,
            score_r["memory_score"],
            novelty_r["novelty_status"],
            recurrence_r,
        )

        # Decide
        decision = memory_qualification_agent.decide(
            cand, score_r["memory_score"],
            novelty_r, recurrence_r, classification,
            min_score=min_memory_score,
        )
        decisions_out.append(decision)

        d_type = decision["decision"]

        if d_type == "quarantine":
            quarantine.append({"candidate": cand, "decision": decision})
            counters["quarantined"] += 1
            audit_entries.append(memory_audit_logger.log(cand, decision, score_r, None, audit_file))
            continue

        if d_type == "ignore_noise":
            counters["ignored"] += 1
            audit_entries.append(memory_audit_logger.log(cand, decision, score_r, None, audit_file))
            continue

        # Validate schema before writing
        test_rec = _preview_record(cand, decision)
        ok, errs = memory_schema_validator.validate(test_rec)
        if not ok:
            decision["decision"] = "quarantine"
            decision["decision_reason"] = f"Schema validation failed: {errs}"
            quarantine.append({"candidate": cand, "decision": decision})
            counters["quarantined"] += 1
            audit_entries.append(memory_audit_logger.log(cand, decision, score_r, None, audit_file))
            continue

        if d_type == "update_existing":
            updates = memory_updater.update(cand, decision, db_dir)
            update_logs.extend(updates)
            counters["updated"] += 1
            audit_entries.append(memory_audit_logger.log(cand, decision, score_r, None, audit_file))
            continue

        if d_type in ("store_as_thesis_update",):
            thesis_rec = thesis_memory_manager.process(
                cand, decision, db_dir / "thesis_memory.jsonl", entity_index
            )
            if thesis_rec:
                thesis_updates.append(thesis_rec)
                counters["thesis"] += 1
            audit_entries.append(memory_audit_logger.log(cand, decision, score_r, thesis_rec, audit_file))
            continue

        # store_new / store_as_watch / store_as_short_term
        rec = memory_writer.write(cand, decision, db_dir)
        if rec:
            new_records.append(rec)
            counters["stored"] += 1
            # If this is a thesis-worthy record, also process thesis
            if decision.get("memory_type") == "thesis_memory":
                thesis_rec = thesis_memory_manager.process(
                    cand, decision, db_dir / "thesis_memory.jsonl", entity_index
                )
                if thesis_rec:
                    thesis_updates.append(thesis_rec)
                    counters["thesis"] += 1
            # Update in-memory indexes so subsequent candidates benefit
            for ent in (cand.get("linked_entities") or []):
                entity_index.setdefault(ent.lower(), []).append(rec["memory_id"])
            for th in (cand.get("linked_themes") or []):
                theme_index.setdefault(th.lower(), []).append(rec["memory_id"])
        audit_entries.append(memory_audit_logger.log(cand, decision, score_r, rec, audit_file))

    print(f"  ✓  stored={counters['stored']}  updated={counters['updated']}  "
          f"ignored={counters['ignored']}  quarantined={counters['quarantined']}  "
          f"thesis={counters['thesis']}")

    # ── Step 9: Apply memory decay ────────────────────────────────────────────
    print("\nStep 9  Running memory decay...")
    decay_report = memory_decay_manager.run_decay(db_dir)
    print(f"  ✓  expired={decay_report['expired_count']}  "
          f"archived={decay_report['archived_count']}  "
          f"stale={decay_report['stale_count']}")

    # ── Step 10: Build memory context packet ──────────────────────────────────
    print("\nStep 10  Building memory context packet...")
    current_entities = list({
        e for c in candidates for e in (c.get("linked_entities") or [])
    })
    current_themes = list({
        t for c in candidates for t in (c.get("linked_themes") or [])
    })
    context_packet = memory_retriever.build_context_packet(
        current_entities, current_themes, db_dir, run_id=run_id
    )
    print(f"  ✓  context packet: {context_packet['summary_stats']['total_relevant']} relevant memories")

    # ── Write all Layer 4 outputs ─────────────────────────────────────────────
    print("\nWriting Layer 4 outputs...")

    out_candidates     = l4_dir / "memory_candidates.json"
    out_decisions      = l4_dir / "memory_decisions.json"
    out_new_records    = l4_dir / "new_memory_records.json"
    out_updated        = l4_dir / "updated_memory_records.json"
    out_thesis         = l4_dir / "thesis_updates.json"
    out_context_packet = l4_dir / "memory_context_packet.json"
    out_decay_report   = l4_dir / "memory_decay_report.json"
    out_quarantine     = l4_dir / "quarantine.json"
    out_quality        = l4_dir / "memory_quality_report.json"
    out_manifest       = l4_dir / "layer4_manifest.json"

    # Strip _obj from candidates before writing (internal field, not needed in output)
    stripped_candidates = [{k: v for k, v in c.items() if k != "_obj"} for c in candidates]

    out_candidates.write_text(json.dumps(stripped_candidates, indent=2))
    out_decisions.write_text(json.dumps(decisions_out, indent=2))
    out_new_records.write_text(json.dumps(new_records, indent=2))
    out_updated.write_text(json.dumps(update_logs, indent=2))
    out_thesis.write_text(json.dumps(thesis_updates, indent=2))
    out_context_packet.write_text(json.dumps(context_packet, indent=2))
    out_decay_report.write_text(json.dumps(decay_report, indent=2))
    out_quarantine.write_text(json.dumps([{k: v for k, v in q.items() if k != "_obj"
                                            for k, v in [(k, ({kk: vv for kk, vv in v.items() if kk != "_obj"} if isinstance(v, dict) else v))]}
                                           for q in quarantine], indent=2))
    out_quarantine.write_text(json.dumps(
        [{"candidate_id": q["candidate"]["candidate_id"],
          "summary": q["candidate"].get("candidate_summary",""),
          "decision": q["decision"]} for q in quarantine],
        indent=2
    ))

    # Quality report
    validation_result = memory_schema_validator.validate_batch(new_records)
    quality_report = {
        "run_id": run_id,
        "total_candidates":  len(candidates),
        "validation":        validation_result,
        "counters":          counters,
        "context_packet_stats": context_packet["summary_stats"],
    }
    out_quality.write_text(json.dumps(quality_report, indent=2))

    # Manifest
    manifest = {
        "layer":    "L4_memory_qualification",
        "run_id":   run_id,
        "status":   "success",
        "generated_at": datetime.now(_IST).isoformat(),
        "memory_candidates":     len(candidates),
        "stored":                counters["stored"],
        "updated":               counters["updated"],
        "ignored":               counters["ignored"],
        "quarantined":           counters["quarantined"],
        "thesis_updates":        counters["thesis"],
        "decay_expired":         decay_report["expired_count"],
        "memory_candidates_path":     str(out_candidates),
        "memory_decisions_path":      str(out_decisions),
        "new_memory_records_path":    str(out_new_records),
        "updated_memory_records_path": str(out_updated),
        "thesis_updates_path":        str(out_thesis),
        "memory_context_packet_path": str(out_context_packet),
        "memory_audit_log_path":      str(DB_MEMORY_AUDIT_INDEX_FILE),
        "memory_decay_report_path":   str(out_decay_report),
        "memory_quality_report_path": str(out_quality),
    }
    out_manifest.write_text(json.dumps(manifest, indent=2))

    print(f"\n{'='*60}")
    print(f"  Layer 4 complete.")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Stored: {counters['stored']}  Updated: {counters['updated']}  "
          f"Ignored: {counters['ignored']}  Quarantined: {counters['quarantined']}")
    print(f"  Thesis records: {counters['thesis']}")
    print(f"  Context packet: {context_packet['summary_stats']['total_relevant']} relevant memories")
    print(f"  Output: {l4_dir}")
    print(f"{'='*60}\n")

    return manifest


def _preview_record(candidate: dict, decision: dict) -> dict:
    """Build a minimal preview record for schema validation (no JSONL write)."""
    from datetime import datetime, timezone, timedelta
    _IST = timezone(timedelta(hours=5, minutes=30))
    now  = datetime.now(_IST).isoformat()
    return {
        "memory_id":    "PREVIEW",
        "memory_type":  decision.get("memory_type", "short_term_market_memory"),
        "status":       "active",
        "title":        candidate.get("candidate_summary", "")[:200],
        "summary":      candidate.get("candidate_summary", ""),
        "created_at":   now,
        "source_refs":  candidate.get("source_refs") or [],
        "confidence":   float(candidate.get("source_confidence", 0.5)),
        "retention":    {"retention_days": decision.get("retention_days", 30)},
    }


def _print_load_summary(summary: dict) -> None:
    for fname, count in summary.items():
        status = "✓" if count > 0 else "–"
        print(f"  {status}  {fname}: {count}")


if __name__ == "__main__":
    target_date = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--date" and i + 1 < len(sys.argv) - 1:
            target_date = sys.argv[i + 2]
        elif arg.startswith("--date="):
            target_date = arg.split("=", 1)[1]

    if target_date:
        from pathlib import Path as _P
        from config import paths as _paths
        # Override with the given date
        _root      = _P(__file__).parent.parent.parent
        _out_dir   = _root / "output" / target_date
        _l3        = _out_dir / "layer3"
        _l4        = _out_dir / "layer4"
        _db        = _root / "db" / "memory"
        run(layer3_dir=_l3, layer4_dir=_l4, db_memory_dir=_db)
    else:
        run()
