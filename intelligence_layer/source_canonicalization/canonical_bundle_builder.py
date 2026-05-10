"""
intelligence_layer/source_canonicalization/canonical_bundle_builder.py — Layer 2

Builds and writes the final Layer 2 output bundle.

Output folder (design doc output folder spec):
    output/{date}/layer2/
    ├── canonical_bundle.json              ← all combined (for Layer 3)
    ├── canonical_documents.json           ← text-based sources
    ├── canonical_structured_records.json  ← data/table sources
    ├── canonical_source_ledger.json       ← per-source metadata + provenance
    ├── duplicate_map.json                 ← duplicate groups
    ├── quality_report.json                ← quality breakdown per source
    ├── quarantine.json                    ← invalid / unprocessable records
    └── layer2_manifest.json              ← run metadata + file paths

Design doc: docs/system_design_docs/layer_2.md  §30 canonical_bundle_builder.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import LAYER2_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def build_source_ledger(
    raw_source_records: list[dict],
    canonical_docs: list[dict],
    canonical_structured: list[dict],
    quarantine: list[dict],
) -> list[dict]:
    """
    Build canonical_source_ledger — one entry per Layer 1 module.

    Design doc §1 canonical_source_ledger schema.
    """
    now_str = datetime.now(_IST).isoformat()
    ledger: list[dict] = []

    for raw_rec in raw_source_records:
        module      = raw_rec.get("source_module") or raw_rec.get("module", "")
        source_type = raw_rec.get("source_type", "")
        status      = raw_rec.get("status", "unknown")

        # Count canonical outputs that came from this module
        canon_docs_count = sum(
            1 for d in canonical_docs
            if d.get("source_type") == source_type
            # Use module matching via source_name if available
        )
        # For structured: module stored in lineage
        canon_struct_count = sum(
            1 for r in canonical_structured
            if r.get("source_type") == source_type
        )
        quar_count = sum(
            1 for q in quarantine
            if q.get("source_module") == module
        )
        raw_count = raw_rec.get("record_count", 0)

        entry = {
            "canonical_source_id": f"CSRC_{module.upper()}",
            "layer1_module":       module,
            "source_type":         source_type,
            "source_name":         raw_rec.get("source_type", module),
            "extraction_phase":    "broad_context",
            "collection_status":   status,
            "record_count_raw":    raw_count,
            "record_count_canonical": canon_docs_count + canon_struct_count,
            "quarantined_count":   quar_count,
            "quality_status":      "usable" if status == "ok" else status,
            "freshness_type":      raw_rec.get("freshness_type", ""),
            "files":               raw_rec.get("files", []),
            "created_at":          now_str,
        }
        ledger.append(entry)
    return ledger


def build_quality_report(
    raw_source_records: list[dict],
    canonical_docs: list[dict],
    canonical_structured: list[dict],
    duplicate_groups: list[dict],
    quarantine: list[dict],
) -> dict:
    """
    Build quality_report matching design doc §quality_report format.
    """
    total_raw_records = sum(r.get("record_count", 0) for r in raw_source_records)
    total_dups = sum(len(g.get("duplicate_document_ids", [])) for g in duplicate_groups)

    # Per-source breakdown for documents
    source_breakdown: dict[str, dict] = {}
    for doc in canonical_docs:
        src = doc.get("source_name") or doc.get("source_type") or "unknown"
        if src not in source_breakdown:
            source_breakdown[src] = {
                "source_name": src, "documents": 0,
                "usable": 0, "partial": 0, "unusable": 0,
            }
        source_breakdown[src]["documents"] += 1
        qs = doc.get("quality_status", "usable")
        if "usable" in qs:
            source_breakdown[src]["usable"] += 1
        elif qs == "partial":
            source_breakdown[src]["partial"] += 1
        else:
            source_breakdown[src]["unusable"] += 1

    total_usable = sum(v["usable"] for v in source_breakdown.values())
    total_docs   = len(canonical_docs) + len(canonical_structured)
    completeness = round(total_usable / total_docs, 3) if total_docs else 0.0

    return {
        "total_raw_source_records":        len(raw_source_records),
        "total_canonical_documents":       len(canonical_docs),
        "total_canonical_structured_records": len(canonical_structured),
        "duplicates_detected":             total_dups,
        "duplicate_groups":                len(duplicate_groups),
        "quarantined_records":             len(quarantine),
        "data_completeness_score":         completeness,
        "quality_by_source":               list(source_breakdown.values()),
    }


def write_bundle(
    canonical_docs:       list[dict],
    canonical_structured: list[dict],
    source_ledger:        list[dict],
    duplicate_groups:     list[dict],
    quality_report:       dict,
    quarantine:           list[dict],
    layer2_dir:           Path = LAYER2_DIR,
) -> dict:
    """
    Write all Layer 2 output files.

    Returns a manifest dict with all output file paths.
    """
    now     = datetime.now(_IST)
    now_str = now.isoformat()
    layer2_dir.mkdir(parents=True, exist_ok=True)

    def _write(filename: str, data) -> Path:
        p = layer2_dir / filename
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return p

    # canonical_documents.json
    docs_file = _write("canonical_documents.json", canonical_docs)

    # canonical_structured_records.json
    struct_file = _write("canonical_structured_records.json", canonical_structured)

    # canonical_source_ledger.json
    ledger_file = _write("canonical_source_ledger.json", source_ledger)

    # duplicate_map.json
    dup_file = _write("duplicate_map.json", duplicate_groups)

    # quality_report.json
    qual_file = _write("quality_report.json", quality_report)

    # quarantine.json
    quar_file = _write("quarantine.json", quarantine)

    # canonical_bundle.json — full combined view (Layer 3 primary input)
    bundle = {
        "layer":                          "L2_source_canonicalization",
        "created_at":                     now_str,
        "total_canonical_documents":      len(canonical_docs),
        "total_canonical_structured_records": len(canonical_structured),
        "canonical_documents":            canonical_docs,
        "canonical_structured_records":   canonical_structured,
        "canonical_source_ledger":        source_ledger,
        "duplicate_map":                  duplicate_groups,
        "quality_summary":                quality_report,
        "quarantine_summary": {
            "quarantined_count": len(quarantine),
        },
    }
    bundle_file = _write("canonical_bundle.json", bundle)

    # layer2_manifest.json
    manifest = {
        "layer":                              "L2_source_canonicalization",
        "status":                             "success",
        "created_at":                         now_str,
        "canonical_bundle_path":              str(bundle_file),
        "canonical_documents_path":           str(docs_file),
        "canonical_structured_records_path":  str(struct_file),
        "canonical_source_ledger_path":       str(ledger_file),
        "duplicate_map_path":                 str(dup_file),
        "quality_report_path":               str(qual_file),
        "quarantine_path":                    str(quar_file),
        "canonical_documents_count":          len(canonical_docs),
        "canonical_structured_records_count": len(canonical_structured),
        "quarantined_count":                  len(quarantine),
    }
    _write("layer2_manifest.json", manifest)

    return manifest
