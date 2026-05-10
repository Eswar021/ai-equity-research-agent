"""
intelligence_layer/source_canonicalization/layer2_runner.py — Layer 2 main entrypoint

Reads raw_context_bundle.json produced by layer1_bundler (or layer7_bundler)
and converts all raw collector outputs into canonical documents and structured
records. Writes the full Layer 2 output contract to output/{date}/layer2/.

Flow (design doc §1 layer2_runner.py):
  1. Load raw_context_bundle.json + raw_source_records.json
  2. For each bundle item:
     a. Look up normalizer in registry
     b. Normalize → list of canonical_document or canonical_structured_record
     c. Assign document_id / record_id
     d. Run quality check
     e. Validate freshness
  3. Deduplicate all canonical_documents (not structured records)
  4. Build source ledger + quality report
  5. Write all output files via canonical_bundle_builder

Usage:
  python intelligence_layer/source_canonicalization/layer2_runner.py
  python intelligence_layer/source_canonicalization/layer2_runner.py --bundle output/2026-05-10/layer1/raw_context_bundle.json
  python intelligence_layer/source_canonicalization/layer2_runner.py --layer7   # canonicalize layer7 instead
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config.paths import LAYER1_DIR, LAYER7_DIR, LAYER2_DIR

from intelligence_layer.source_canonicalization import normalizer_registry
from intelligence_layer.source_canonicalization.content_quality_checker import check_quality
from intelligence_layer.source_canonicalization.freshness_validator      import validate_freshness
from intelligence_layer.source_canonicalization.deduplicator             import deduplicate
from intelligence_layer.source_canonicalization.canonical_bundle_builder import (
    build_source_ledger, build_quality_report, write_bundle,
)

_IST = timezone(timedelta(hours=5, minutes=30))


# ── ID generators ─────────────────────────────────────────────────────────────

def _make_id_generator(prefix: str):
    counter = [0]
    today = datetime.now(_IST).strftime("%Y%m%d")
    def _next() -> str:
        counter[0] += 1
        return f"{prefix}_{today}_{counter[0]:05d}"
    return _next

_next_doc_id  = _make_id_generator("DOC")
_next_srec_id = _make_id_generator("SREC")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ✗  Cannot load {path.name}: {e}")
        return {}


def _find_bundle(layer_dir: Path) -> tuple[Path | None, Path | None]:
    """Locate raw_context_bundle (or raw_deep_dive_bundle) and raw_source_records."""
    bundle = layer_dir / "raw_context_bundle.json"
    if not bundle.exists():
        bundle = layer_dir / "raw_deep_dive_bundle.json"
    sources = layer_dir / "raw_source_records.json"
    return (bundle if bundle.exists() else None,
            sources if sources.exists() else None)


# ── Core normalizer dispatcher ────────────────────────────────────────────────

def _normalize_item(item: dict) -> tuple[list[dict], list[dict], dict | None]:
    """
    Normalize one bundle item into canonical records.

    Returns:
        (canonical_documents, canonical_structured_records, quarantine_entry | None)
    """
    module      = item.get("source_module", "")
    source_type = item.get("source_type", "")
    freshness   = item.get("freshness_type", "historical_available")
    content     = item.get("content")

    if content is None:
        return [], [], {
            "source_module": module,
            "reason":        "null_content_in_bundle",
            "raw_reference": item.get("source_file", ""),
        }

    entry = normalizer_registry.lookup(module)
    if entry is None:
        return [], [], {
            "source_module": module,
            "source_type":   source_type,
            "reason":        f"no_normalizer_registered_for_module:{module}",
            "raw_reference": item.get("source_file", ""),
        }

    normalizer_fn, record_kind, source_display_name = entry

    try:
        if record_kind == "document":
            # Text normalizers: fn(content, module, source_name) → list[dict]
            records = normalizer_fn(content, module, source_display_name)
            docs: list[dict] = []
            for rec in records:
                rec["document_id"] = _next_doc_id()
                rec["freshness"]   = validate_freshness(
                    freshness_type = freshness,
                    source_type    = rec.get("source_type", source_type),
                    published_at   = rec.get("published_at"),
                    collected_at   = item.get("collected_at"),
                )
                quality = check_quality(rec, kind="document")
                rec["quality_score"]  = quality["quality_score"]
                rec["quality_status"] = quality["quality_status"]
                rec["quality_warnings"] = quality["warnings"]
                rec["lineage"] = {
                    "source_file":  item.get("source_file", ""),
                    "source_module": module,
                }
                docs.append(rec)
            return docs, [], None

        else:  # structured
            # Structured normalizers: fn(content, module) → list[dict]
            # Some structured normalizers need extra context (e.g. market for macro)
            if module in ("india_macro",):
                records = normalizer_fn(content, module, market="india")
            elif module in ("us_macro",):
                records = normalizer_fn(content, module, market="us")
            else:
                records = normalizer_fn(content, module)

            structs: list[dict] = []
            for rec in records:
                rec["record_id"] = _next_srec_id()
                if "freshness" not in rec:
                    rec["freshness"] = validate_freshness(
                        freshness_type = freshness,
                        source_type    = rec.get("source_type", source_type),
                        collected_at   = item.get("collected_at"),
                    )
                quality = check_quality(rec, kind="structured")
                rec["quality_score"]    = quality["quality_score"]
                rec["quality_status"]   = quality["quality_status"]
                rec["quality_warnings"] = quality.get("warnings", [])
                rec["missing_fields"]   = quality.get("missing_fields", [])
                rec["lineage"] = {
                    "source_file":   item.get("source_file", ""),
                    "source_module": module,
                }
                structs.append(rec)
            return [], structs, None

    except Exception as e:
        return [], [], {
            "source_module": module,
            "reason":        f"normalizer_exception: {e}",
            "raw_reference": item.get("source_file", ""),
        }


# ── Main runner ───────────────────────────────────────────────────────────────

def run(
    layer_dir:  Path = LAYER1_DIR,
    layer2_dir: Path = LAYER2_DIR,
    verbose:    bool = True,
) -> dict:
    """
    Run the full Layer 2 canonicalization pipeline.

    Args:
        layer_dir:  directory containing raw_context_bundle.json (LAYER1_DIR or LAYER7_DIR)
        layer2_dir: output directory (LAYER2_DIR)
        verbose:    print progress

    Returns:
        manifest dict with all output file paths (design doc §1 output schema)
    """
    start = datetime.now(_IST)
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  Layer 2 — Source Canonicalization")
        print(f"  {start.strftime('%d %b %Y  %I:%M %p IST')}")
        print(f"{'═'*60}")

    # ── Load Layer 1 outputs ──────────────────────────────────────────────────
    bundle_path, src_records_path = _find_bundle(layer_dir)
    if not bundle_path:
        print(f"  ✗  No bundle file found in {layer_dir}. Run Layer 1 first.")
        return {}

    if verbose:
        print(f"\n  Loading: {bundle_path.name}")

    bundle_data   = _load_json(bundle_path)
    src_records   = _load_json(src_records_path) if src_records_path else []

    items = bundle_data.get("items") if isinstance(bundle_data, dict) else []
    if not items:
        print("  ✗  Bundle has no items. Nothing to canonicalize.")
        return {}

    if verbose:
        print(f"  Items in bundle  : {len(items)}")
        print(f"  Source records   : {len(src_records)}")

    # ── Normalize all items ───────────────────────────────────────────────────
    all_docs:       list[dict] = []
    all_structured: list[dict] = []
    all_quarantine: list[dict] = []

    module_stats: dict[str, dict] = {}

    for item in items:
        module = item.get("source_module", "unknown")
        stats  = module_stats.setdefault(module, {"docs": 0, "structs": 0, "quarantined": 0})

        docs, structs, quar = _normalize_item(item)
        all_docs.extend(docs)
        all_structured.extend(structs)
        stats["docs"]    += len(docs)
        stats["structs"] += len(structs)
        if quar:
            all_quarantine.append(quar)
            stats["quarantined"] += 1

    if verbose:
        print(f"\n  Normalized:")
        print(f"    canonical_documents        : {len(all_docs)}")
        print(f"    canonical_structured_records: {len(all_structured)}")
        print(f"    quarantined                : {len(all_quarantine)}")

    # ── Deduplicate documents ─────────────────────────────────────────────────
    if verbose:
        print(f"\n  Running deduplication on {len(all_docs)} documents...")

    all_docs, dup_groups = deduplicate(all_docs)
    total_dups = sum(len(g.get("duplicate_document_ids", [])) for g in dup_groups)

    if verbose:
        print(f"    Duplicate groups : {len(dup_groups)}")
        print(f"    Duplicate docs   : {total_dups}")

    # ── Build source ledger + quality report ──────────────────────────────────
    src_records_list = src_records if isinstance(src_records, list) else []
    source_ledger = build_source_ledger(
        src_records_list, all_docs, all_structured, all_quarantine
    )
    quality_report = build_quality_report(
        src_records_list, all_docs, all_structured, dup_groups, all_quarantine
    )

    # ── Write outputs ─────────────────────────────────────────────────────────
    manifest = write_bundle(
        canonical_docs       = all_docs,
        canonical_structured = all_structured,
        source_ledger        = source_ledger,
        duplicate_groups     = dup_groups,
        quality_report       = quality_report,
        quarantine           = all_quarantine,
        layer2_dir           = layer2_dir,
    )

    elapsed = (datetime.now(_IST) - start).seconds
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  Layer 2 complete — {elapsed}s")
        print(f"  canonical_documents        : {len(all_docs)}")
        print(f"  canonical_structured_records: {len(all_structured)}")
        print(f"  duplicates removed         : {total_dups}")
        print(f"  quarantined                : {len(all_quarantine)}")
        print(f"  completeness score         : {quality_report.get('data_completeness_score', 0):.2f}")
        print(f"  Output → {layer2_dir}")
        print(f"{'═'*60}\n")

    return manifest


# ── Per-module summary ────────────────────────────────────────────────────────

def _print_module_stats(module_stats: dict[str, dict]) -> None:
    print(f"\n  {'Module':25s}  {'Docs':6}  {'Structs':8}  {'Quarantined':11}")
    print(f"  {'─'*55}")
    for mod, st in sorted(module_stats.items()):
        print(f"  {mod:25s}  {st['docs']:6}  {st['structs']:8}  {st['quarantined']:11}")


if __name__ == "__main__":
    use_layer7 = "--layer7" in sys.argv

    bundle_override = None
    for arg in sys.argv[1:]:
        if arg.startswith("--bundle="):
            bundle_override = Path(arg.split("=", 1)[1])
        elif arg == "--bundle" and sys.argv.index(arg) + 1 < len(sys.argv):
            bundle_override = Path(sys.argv[sys.argv.index(arg) + 1])

    if bundle_override:
        src_dir = bundle_override.parent
    elif use_layer7:
        src_dir = LAYER7_DIR
    else:
        src_dir = LAYER1_DIR

    result = run(layer_dir=src_dir, layer2_dir=LAYER2_DIR, verbose=True)
    if result:
        print(f"  Manifest → {src_dir.parent / 'layer2' / 'layer2_manifest.json'}")
