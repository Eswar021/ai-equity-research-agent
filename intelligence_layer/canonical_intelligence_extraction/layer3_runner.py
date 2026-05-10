"""
intelligence_layer/canonical_intelligence_extraction/layer3_runner.py — Layer 3

Main controller for the Canonical Intelligence Extraction pipeline.

Exact workflow (design doc §1, internal architecture diagram):
  1.  canonical_input_loader        — load Layer 2 canonical outputs
  2.  document_router               — route text documents to extraction profiles
  3.  extraction_chunker            — split long documents into chunks
  4.  prompt_registry + llm_json_client — LLM extraction (one call per chunk)
      → entity_extractor, fact_extractor, claim_extractor, event_extractor   (text path)
  5.  theme_extractor.aggregate_themes() — cross-document theme aggregation
  6.  structured_record_router      — route structured records
      → structured_fact_extractor, market_signal_builder,
        filing_metadata_extractor, numeric_observation_extractor (structured path)
  7.  entity_resolver_light         — ticker enrichment
  8.  intelligence_object_linker    — link objects across types
  9.  confidence_scorer             — adjust confidence
  10. contradiction_hint_detector   — flag obvious contradictions
  11. object_deduplicator           — merge duplicate objects
  12. hallucination_precheck        — downgrade unsupported objects
  13. schema_validator              — validate taxonomy / required fields
  14. source_ref_validator          — validate every object links to Layer 2
  15. valid → intelligence_bundle_builder
      invalid → quarantine_writer

Usage:
  python intelligence_layer/canonical_intelligence_extraction/layer3_runner.py
  python intelligence_layer/canonical_intelligence_extraction/layer3_runner.py --layer7
  python intelligence_layer/canonical_intelligence_extraction/layer3_runner.py --provider openai

Design doc: docs/system_design_docs/layer_3.md
"""

from __future__ import annotations
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import LAYER2_DIR, LAYER7_DIR, LAYER3_DIR, LAYER3_LLM_LOGS_DIR

# ── Layer 3 modules (exact workflow order) ────────────────────────────────────
from intelligence_layer.canonical_intelligence_extraction.canonical_input_loader import load as l2_load
from intelligence_layer.canonical_intelligence_extraction.document_router import route_all as route_docs, route
from intelligence_layer.canonical_intelligence_extraction.structured_record_router import route_all as route_structs
from intelligence_layer.canonical_intelligence_extraction.extraction_chunker import chunk as chunk_doc
from intelligence_layer.canonical_intelligence_extraction.prompt_registry import get_schema
from intelligence_layer.canonical_intelligence_extraction import llm_json_client

_HEADLINE_BATCH_SIZE = 8   # short docs packed into one LLM call

from intelligence_layer.canonical_intelligence_extraction.extractors.entity_extractor import format_entities
from intelligence_layer.canonical_intelligence_extraction.extractors.fact_extractor   import format_facts
from intelligence_layer.canonical_intelligence_extraction.extractors.claim_extractor  import format_claims
from intelligence_layer.canonical_intelligence_extraction.extractors.event_extractor  import format_events
from intelligence_layer.canonical_intelligence_extraction.extractors.theme_extractor  import format_themes, aggregate_themes

from intelligence_layer.canonical_intelligence_extraction.extractors.structured_fact_extractor    import extract as sfact_extract
from intelligence_layer.canonical_intelligence_extraction.extractors.market_signal_builder        import build  as signal_build
from intelligence_layer.canonical_intelligence_extraction.extractors.filing_metadata_extractor    import extract as filing_extract
from intelligence_layer.canonical_intelligence_extraction.extractors.numeric_observation_extractor import extract as numobs_extract

from intelligence_layer.canonical_intelligence_extraction.post_processors.entity_resolver_light        import resolve_all
from intelligence_layer.canonical_intelligence_extraction.post_processors.intelligence_object_linker   import link as link_objects
from intelligence_layer.canonical_intelligence_extraction.post_processors.confidence_scorer            import score_all
from intelligence_layer.canonical_intelligence_extraction.post_processors.contradiction_hint_detector  import detect as detect_contradictions
from intelligence_layer.canonical_intelligence_extraction.post_processors.object_deduplicator         import dedup_all

from intelligence_layer.canonical_intelligence_extraction.validators.hallucination_precheck import precheck_all
from intelligence_layer.canonical_intelligence_extraction.validators.schema_validator       import validate_all
from intelligence_layer.canonical_intelligence_extraction.validators.source_ref_validator   import validate as srval, build_id_sets

from intelligence_layer.canonical_intelligence_extraction.quarantine_writer         import QuarantineWriter
from intelligence_layer.canonical_intelligence_extraction.intelligence_bundle_builder import (
    build_extraction_quality_report, write_bundle,
)

_IST = timezone(timedelta(hours=5, minutes=30))
_log_lock = threading.Lock()


# ── Structured extractor dispatcher ──────────────────────────────────────────

_STRUCT_EXTRACTOR_FNS = {
    "structured_fact_extractor":     sfact_extract,
    "market_signal_builder":         signal_build,
    "filing_metadata_extractor":     filing_extract,
    "numeric_observation_extractor": numobs_extract,
}


def _run_structured_extractors(record: dict, extractor_names: list[str]) -> tuple[list, list, list]:
    """Call the appropriate structured extractors for one record."""
    all_facts   = []
    all_signals = []
    all_events  = []
    for name in extractor_names:
        fn = _STRUCT_EXTRACTOR_FNS.get(name)
        if fn is None:
            continue
        result = fn(record)
        if name in ("structured_fact_extractor", "numeric_observation_extractor"):
            # Mark as rule-based so confidence_scorer gives them high baseline
            for item in result:
                item["_extraction_source"] = "rule"
            all_facts.extend(result)
        elif name == "market_signal_builder":
            for item in result:
                item["_extraction_source"] = "rule"
            all_signals.extend(result)
        elif name == "filing_metadata_extractor":
            for item in result:
                item["_extraction_source"] = "rule"
            all_events.extend(result)
    return all_facts, all_signals, all_events


# ── Batch extraction for headline documents ───────────────────────────────────

def _process_headline_batch(
    decisions:      list[dict],
    doc_by_id:      dict,
    batch_pipeline,
    log_path:       Path | None,
) -> tuple[list, list, list, list, list]:
    """
    Extract intelligence from a batch of short headline docs in one LLM call.
    Packs up to _HEADLINE_BATCH_SIZE articles into a single prompt.
    Maps results back to individual documents via article_index.
    """
    docs  = [doc_by_id.get(d["document_id"], {}) for d in decisions]
    parts = []
    for i, doc in enumerate(docs):
        text = (doc.get("clean_text") or "")[:500]
        parts.append(f"=== Article {i} ===\n{text}")
    combined = "\n\n".join(parts)

    batch_result = llm_json_client.extract_batch(batch_pipeline, combined)
    if batch_result is None:
        return [], [], [], [], []

    all_entities, all_facts, all_claims, all_events, all_themes = [], [], [], [], []

    for article_result in batch_result.articles:
        idx = article_result.article_index
        if not (0 <= idx < len(docs)):
            continue
        doc    = docs[idx]
        if not doc:
            continue
        # Synthetic chunk — source_ref points to the correct document
        chunk  = {
            "chunk_id":     f"{doc.get('document_id', '')}__batch",
            "chunk_index":  0,
            "total_chunks": 1,
            "section":      "headline",
            "text":         parts[idx].split("\n", 1)[1] if "\n" in parts[idx] else parts[idx],
        }
        all_entities.extend(format_entities(article_result.entities, doc, chunk))
        all_facts.extend(format_facts(article_result.facts,           doc, chunk))
        all_claims.extend(format_claims(article_result.claims,        doc, chunk))
        all_events.extend(format_events(article_result.events,        doc, chunk))
        all_themes.extend(format_themes(article_result.themes,        doc, chunk))

    if log_path:
        record = {
            "ts":          datetime.now(_IST).isoformat(),
            "batch_size":  len(decisions),
            "doc_ids":     [d["document_id"] for d in decisions],
            "entities":    sum(len(a.entities) for a in batch_result.articles),
            "events":      sum(len(a.events)   for a in batch_result.articles),
        }
        with _log_lock:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return all_entities, all_facts, all_claims, all_events, all_themes


# ── LLM extraction for one document ──────────────────────────────────────────

def _extract_one_doc(
    doc: dict,
    pipeline_cache: dict,    # profile → pipeline (built once, reused)
    llm,
    log_path: Path | None,
) -> tuple[list, list, list, list, list]:
    """
    Run LLM extraction on one canonical document.

    Returns:
        (raw_entities, raw_facts, raw_claims, raw_events, raw_themes)
        All items are formatted by the individual extractor functions.
    """
    routing = route(doc)
    if routing["skip"]:
        return [], [], [], [], []

    profile  = routing["extraction_profile"]
    if profile not in pipeline_cache:
        pipeline_cache[profile] = llm_json_client.build_pipeline(llm, profile)
    pipeline = pipeline_cache[profile]

    chunks = chunk_doc(doc, routing)
    if not chunks:
        return [], [], [], [], []

    doc_entities: list = []
    doc_facts:    list = []
    doc_claims:   list = []
    doc_events:   list = []
    doc_themes:   list = []

    for chunk in chunks:
        result = llm_json_client.extract(pipeline, chunk["text"])
        if result is None:
            if log_path:
                _log_llm_call(log_path, doc, chunk, error="extraction_returned_none")
            continue

        if log_path:
            _log_llm_call(log_path, doc, chunk, result=result)

        doc_entities.extend(format_entities(result.entities, doc, chunk))
        doc_facts.extend(format_facts(result.facts,       doc, chunk))
        doc_claims.extend(format_claims(result.claims,    doc, chunk))
        doc_events.extend(format_events(result.events,    doc, chunk))
        doc_themes.extend(format_themes(result.themes,    doc, chunk))

    return doc_entities, doc_facts, doc_claims, doc_events, doc_themes


def _log_llm_call(log_path: Path, doc: dict, chunk: dict, result=None, error: str = "") -> None:
    record = {
        "ts":           datetime.now(_IST).isoformat(),
        "document_id":  doc.get("document_id", ""),
        "source_name":  doc.get("source_name", ""),
        "chunk_id":     chunk.get("chunk_id", ""),
        "chunk_chars":  len(chunk.get("text", "")),
        "entities":     len(result.entities)  if result else 0,
        "facts":        len(result.facts)     if result else 0,
        "claims":       len(result.claims)    if result else 0,
        "events":       len(result.events)    if result else 0,
        "themes":       len(result.themes)    if result else 0,
        "error":        error,
    }
    with _log_lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Main runner ───────────────────────────────────────────────────────────────

def run(
    layer2_dir:  Path = LAYER2_DIR,
    layer3_dir:  Path = LAYER3_DIR,
    llm          = None,
    max_workers: int  = 50,
    verbose:     bool = True,
) -> dict:
    """
    Run the full Layer 3 Canonical Intelligence Extraction pipeline.

    Args:
        layer2_dir:  Layer 2 output directory (LAYER2_DIR or LAYER7_DIR for second pass)
        layer3_dir:  Layer 3 output directory
        llm:         LangChain LLM (default: Gemini Flash via make_llm)
        max_workers: concurrent LLM workers
        verbose:     print progress

    Returns:
        layer3_manifest dict with all output file paths.
    """
    start = datetime.now(_IST)
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  Layer 3 — Canonical Intelligence Extraction")
        print(f"  {start.strftime('%d %b %Y  %I:%M %p IST')}")
        print(f"{'═'*60}")

    # ── Step 1: Load Layer 2 outputs ──────────────────────────────────────────
    if verbose:
        print(f"\n  [1/14] Loading Layer 2 from {layer2_dir.name} …")
    l2 = l2_load(layer2_dir)
    stats = l2["stats"]
    if verbose:
        print(f"    Documents  passed:    {stats['docs_passed']}")
        print(f"    Docs skipped (dup):   {stats['docs_skipped_duplicate']}")
        print(f"    Docs skipped (bad):   {stats['docs_skipped_unusable']}")
        print(f"    Structured records:   {stats['structured_records']}")

    documents   = l2["documents"]
    structs     = l2["structured_records"]
    src_ledger  = l2["source_ledger"]

    if not documents and not structs:
        print("  ✗  No content to process. Run Layer 2 first.")
        return {}

    # Build source ID sets for validation
    doc_ids, rec_ids = build_id_sets(documents, structs)

    # Document quality map for confidence scorer
    doc_quality_map = {
        d.get("document_id", ""): float(d.get("quality_score", 0.7))
        for d in documents
    }

    # ── Step 2: Route text documents ─────────────────────────────────────────
    if verbose:
        print(f"\n  [2/14] Routing {len(documents)} documents …")
    routed_docs, skipped_docs = route_docs(documents)
    if verbose:
        print(f"    Routed: {len(routed_docs)}   Skipped (no text): {len(skipped_docs)}")

    # ── Step 3: LLM extraction (steps 3+4 from design doc) ───────────────────
    if llm is None:
        from llm.llm_client import make_llm
        llm = make_llm(provider="openai", temperature=0.05)

    LAYER3_LLM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    log_path = LAYER3_LLM_LOGS_DIR / f"extraction_{today}.jsonl"

    if verbose:
        print(f"\n  [3+4/14] LLM extraction on {len(routed_docs)} docs "
              f"({max_workers} workers) …")
        print(f"    LLM log → {log_path}")

    # Build a doc_id → doc map for quick access
    doc_by_id = {d.get("document_id", ""): d for d in documents}

    all_entities: list[dict] = []
    all_facts:    list[dict] = []
    all_claims:   list[dict] = []
    all_events:   list[dict] = []
    raw_themes:   list[dict] = []
    llm_failed    = 0
    pipeline_cache: dict = {}
    pipeline_lock  = threading.Lock()

    # ── Split: batch short headlines vs individual full-text docs ─────────────
    headline_decisions = [d for d in routed_docs if d["extraction_profile"] == "headline_extraction"]
    full_decisions     = [d for d in routed_docs if d["extraction_profile"] != "headline_extraction"]

    # Batch headlines into groups of _HEADLINE_BATCH_SIZE
    headline_batches = [
        headline_decisions[i: i + _HEADLINE_BATCH_SIZE]
        for i in range(0, len(headline_decisions), _HEADLINE_BATCH_SIZE)
    ]

    total_tasks = len(full_decisions) + len(headline_batches)
    if verbose:
        print(f"    Full-text docs: {len(full_decisions)}  |  "
              f"Headline batches: {len(headline_batches)} "
              f"({len(headline_decisions)} headlines → {_HEADLINE_BATCH_SIZE}/batch)  |  "
              f"Total tasks: {total_tasks}")

    # ── Per-full-doc worker ────────────────────────────────────────────────────
    def _process_doc(decision: dict) -> tuple:
        doc_id = decision["document_id"]
        doc    = doc_by_id.get(doc_id, {})
        if not doc:
            return [], [], [], [], []
        with pipeline_lock:
            profile = decision["extraction_profile"]
            if profile not in pipeline_cache:
                pipeline_cache[profile] = llm_json_client.build_pipeline(llm, profile)
        chunks = chunk_doc(doc, decision)
        if not chunks:
            return [], [], [], [], []
        doc_entities, doc_facts, doc_claims, doc_events, doc_themes = [], [], [], [], []
        for chunk in chunks:
            pipeline = pipeline_cache[decision["extraction_profile"]]
            result   = llm_json_client.extract(pipeline, chunk["text"])
            if result is None:
                _log_llm_call(log_path, doc, chunk, error="llm_returned_none")
                continue
            _log_llm_call(log_path, doc, chunk, result=result)
            doc_entities.extend(format_entities(result.entities, doc, chunk))
            doc_facts.extend(format_facts(result.facts,           doc, chunk))
            doc_claims.extend(format_claims(result.claims,        doc, chunk))
            doc_events.extend(format_events(result.events,        doc, chunk))
            doc_themes.extend(format_themes(result.themes,        doc, chunk))
        return doc_entities, doc_facts, doc_claims, doc_events, doc_themes

    # ── Per-batch worker ───────────────────────────────────────────────────────
    def _process_batch(batch_decisions: list[dict]) -> tuple:
        with pipeline_lock:
            if "batch_headline_extraction" not in pipeline_cache:
                pipeline_cache["batch_headline_extraction"] = llm_json_client.build_batch_pipeline(llm)
        batch_pipeline = pipeline_cache["batch_headline_extraction"]
        return _process_headline_batch(batch_decisions, doc_by_id, batch_pipeline, log_path)

    # ── Submit all tasks to thread pool ───────────────────────────────────────
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map: dict = {}
        for d in full_decisions:
            future_map[executor.submit(_process_doc, d)] = f"doc:{d['document_id']}"
        for batch in headline_batches:
            future_map[executor.submit(_process_batch, batch)] = "batch"

        for future in as_completed(future_map):
            try:
                ents, fcts, clms, evts, thms = future.result()
                all_entities.extend(ents)
                all_facts.extend(fcts)
                all_claims.extend(clms)
                all_events.extend(evts)
                raw_themes.extend(thms)
            except Exception as e:
                llm_failed += 1
                if verbose:
                    print(f"  ✗  {future_map[future]}: {e}")
            completed += 1
            if verbose and completed % 10 == 0:
                print(f"    {completed}/{total_tasks} tasks done …")

    if verbose:
        print(f"    Extracted: {len(all_entities)} entities, {len(all_facts)} facts, "
              f"{len(all_claims)} claims, {len(all_events)} events, {len(raw_themes)} themes (raw)")

    # ── Step 5: Theme aggregation (cross-document) ────────────────────────────
    if verbose:
        print(f"\n  [5/14] Aggregating themes across documents …")
    all_themes = aggregate_themes(raw_themes)
    if verbose:
        print(f"    {len(raw_themes)} raw → {len(all_themes)} aggregated themes")

    # ── Step 6: Structured record extraction ──────────────────────────────────
    if verbose:
        print(f"\n  [6/14] Structured extraction on {len(structs)} records …")
    struct_decisions = route_structs(structs)
    struct_by_id = {r.get("record_id", ""): r for r in structs}

    struct_facts:   list[dict] = []
    struct_signals: list[dict] = []
    struct_events:  list[dict] = []

    for decision in struct_decisions:
        record = struct_by_id.get(decision["record_id"]) or {}
        if not record:
            continue
        fcts, sigs, evts = _run_structured_extractors(record, decision["extractors"])
        struct_facts.extend(fcts)
        struct_signals.extend(sigs)
        struct_events.extend(evts)

    all_facts.extend(struct_facts)
    all_events.extend(struct_events)
    all_signals = struct_signals

    if verbose:
        print(f"    Structured: {len(struct_facts)} facts, {len(all_signals)} signals, {len(struct_events)} events")

    # ── Step 7: Entity resolution ─────────────────────────────────────────────
    if verbose:
        print(f"\n  [7/14] Resolving {len(all_entities)} entities …")
    all_entities, unresolved_entities = resolve_all(all_entities)
    resolved_count = len(all_entities) - len(unresolved_entities)
    if verbose:
        print(f"    Resolved: {resolved_count}   Unresolved: {len(unresolved_entities)}")

    # ── Step 8: Object linking ────────────────────────────────────────────────
    if verbose:
        print(f"\n  [8/14] Linking intelligence objects …")
    object_link_map = link_objects(
        all_entities, all_facts, all_claims, all_events, all_themes, all_signals)
    if verbose:
        print(f"    {len(object_link_map)} links created")

    # ── Step 9: Confidence scoring ────────────────────────────────────────────
    if verbose:
        print(f"\n  [9/14] Scoring confidence …")
    score_all(all_entities, all_facts, all_claims, all_events, all_themes, all_signals,
              doc_quality_map=doc_quality_map)

    # ── Step 10: Contradiction detection ─────────────────────────────────────
    if verbose:
        print(f"\n  [10/14] Detecting contradiction hints …")
    contradiction_hints = detect_contradictions(all_claims, all_facts, all_signals)
    if verbose:
        print(f"    {len(contradiction_hints)} contradiction hints")

    # ── Step 11: Object deduplication ────────────────────────────────────────
    if verbose:
        print(f"\n  [11/14] Deduplicating intelligence objects …")
    all_entities, all_facts, all_claims, all_events, dedup_map = dedup_all(
        all_entities, all_facts, all_claims, all_events)
    if verbose:
        print(f"    After dedup: {len(all_entities)} entities, {len(all_facts)} facts, "
              f"{len(all_claims)} claims, {len(all_events)} events")

    # ── Step 12: Hallucination precheck ──────────────────────────────────────
    if verbose:
        print(f"\n  [12/14] Hallucination precheck …")
    precheck_warnings = precheck_all(all_entities, all_facts, all_claims, all_events, all_themes)
    if verbose:
        print(f"    {len(precheck_warnings)} objects flagged")

    # ── Step 13: Schema validation ────────────────────────────────────────────
    if verbose:
        print(f"\n  [13/14] Schema validation …")
    valid_sets, schema_invalid = validate_all(
        all_entities, all_facts, all_claims, all_events, all_themes, all_signals)

    # ── Step 14: Source reference validation ──────────────────────────────────
    if verbose:
        print(f"\n  [14/14] Source reference validation …")
    quarantine = QuarantineWriter()
    quarantine.add_many(schema_invalid)

    final_entities = []
    final_facts    = []
    final_claims   = []
    final_events   = []
    final_themes   = []
    final_signals  = []

    for obj_type, obj_list, target_list in [
        ("entity",  valid_sets["entities"], final_entities),
        ("fact",    valid_sets["facts"],    final_facts),
        ("claim",   valid_sets["claims"],   final_claims),
        ("event",   valid_sets["events"],   final_events),
        ("theme",   valid_sets["themes"],   final_themes),
        ("signal",  valid_sets["signals"],  final_signals),
    ]:
        valid_obj, invalid_obj = srval(obj_list, doc_ids, rec_ids, src_ledger)
        target_list.extend(valid_obj)
        for inv in invalid_obj:
            obj_id = (inv.get("entity_id") or inv.get("fact_id") or inv.get("claim_id")
                      or inv.get("event_id") or inv.get("theme_id")
                      or inv.get("signal_id") or "unknown")
            quarantine.add(obj_type, obj_id,
                           inv.get("validation_error", "source_ref_invalid"), inv)

    quarantine.write(layer3_dir)

    if verbose:
        print(f"    Valid: {len(final_entities)} entities, {len(final_facts)} facts, "
              f"{len(final_claims)} claims, {len(final_events)} events, "
              f"{len(final_themes)} themes, {len(final_signals)} signals")
        print(f"    Quarantined: {quarantine.count()} objects")

    # ── Write outputs ─────────────────────────────────────────────────────────
    quality_report = build_extraction_quality_report(
        docs_processed       = stats["docs_passed"],
        structs_processed    = stats["structured_records"],
        docs_skipped_dup     = stats["docs_skipped_duplicate"],
        docs_skipped_quality = stats["docs_skipped_unusable"],
        llm_docs_processed   = len(routed_docs) - llm_failed,
        llm_failed           = llm_failed,
        entities             = final_entities,
        facts                = final_facts,
        claims               = final_claims,
        events               = final_events,
        themes               = final_themes,
        signals              = final_signals,
        quarantine_count     = quarantine.count(),
        precheck_warnings    = precheck_warnings,
        contradiction_hints  = contradiction_hints,
    )

    manifest = write_bundle(
        entities            = final_entities,
        facts               = final_facts,
        claims              = final_claims,
        events              = final_events,
        themes              = final_themes,
        signals             = final_signals,
        unresolved_entities = unresolved_entities,
        object_link_map     = object_link_map + dedup_map,
        contradiction_hints = contradiction_hints,
        quality_report      = quality_report,
        layer3_dir          = layer3_dir,
    )

    elapsed = (datetime.now(_IST) - start).seconds
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  Layer 3 complete — {elapsed}s")
        print(f"  Entities     : {len(final_entities)}")
        print(f"  Facts        : {len(final_facts)}")
        print(f"  Claims       : {len(final_claims)}")
        print(f"  Events       : {len(final_events)}")
        print(f"  Themes       : {len(final_themes)}")
        print(f"  Signals      : {len(final_signals)}")
        print(f"  Quarantined  : {quarantine.count()}")
        print(f"  Output → {layer3_dir}")
        print(f"{'═'*60}\n")

    return manifest


if __name__ == "__main__":
    use_layer7  = "--layer7" in sys.argv
    provider    = "openai"
    max_workers = 50
    args        = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
        elif arg == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
        elif arg.startswith("--workers="):
            max_workers = int(arg.split("=", 1)[1])
        elif arg == "--workers" and i + 1 < len(args):
            max_workers = int(args[i + 1])

    src_dir = LAYER7_DIR if use_layer7 else LAYER2_DIR

    from llm.llm_client import make_llm
    llm = make_llm(provider=provider, temperature=0.05)

    result = run(layer2_dir=src_dir, layer3_dir=LAYER3_DIR, llm=llm,
                 max_workers=max_workers, verbose=True)
    if result:
        print(f"  Manifest → {LAYER3_DIR / 'layer3_manifest.json'}")
