"""
intelligence_layer/canonical_intelligence_extraction/canonical_input_loader.py — Layer 3

Loads Layer 2 canonical outputs and filters them to produce the working set for
Layer 3 extraction.

Filtering rules (design doc §2 canonical_input_loader.py):
  - Skip documents where duplicate_status.is_duplicate == True
    (those are non-canonical duplicates; the canonical copy is already present)
  - Skip documents where quality_status == "unusable"
  - Structured records are never deduplicated (all pass through)

Design doc: docs/system_design_docs/layer_3.md §2 canonical_input_loader.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import LAYER2_DIR


def load(
    layer2_dir: Path = LAYER2_DIR,
    include_partial: bool = True,
) -> dict:
    """
    Load Layer 2 outputs and return filtered working set for Layer 3.

    Args:
        layer2_dir:      Path to Layer 2 output directory.
        include_partial: If True, include documents with quality_status="partial".
                         If False, only "usable" and "usable_with_warnings" pass.

    Returns:
        {
          "documents":        list[dict],   # text canonical docs (filtered)
          "structured_records": list[dict], # all structured records (no filter)
          "source_ledger":    list[dict],
          "duplicate_map":    list[dict],
          "quality_report":   dict,
          "stats": {
              "total_docs_raw":        int,
              "docs_skipped_duplicate": int,
              "docs_skipped_unusable":  int,
              "docs_passed":           int,
              "structured_records":    int,
          }
        }
    """
    # ── locate files ──────────────────────────────────────────────────────────
    bundle_path  = layer2_dir / "canonical_bundle.json"
    docs_path    = layer2_dir / "canonical_documents.json"
    struct_path  = layer2_dir / "canonical_structured_records.json"
    ledger_path  = layer2_dir / "canonical_source_ledger.json"
    dup_path     = layer2_dir / "duplicate_map.json"
    quality_path = layer2_dir / "quality_report.json"

    def _read(p: Path, default):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ✗  layer3 loader: cannot read {p.name}: {e}")
                return default
        return default

    # Prefer individual files; fall back to canonical_bundle.json
    if docs_path.exists():
        raw_docs    = _read(docs_path,    [])
        raw_structs = _read(struct_path,  [])
    elif bundle_path.exists():
        bundle      = _read(bundle_path,  {})
        raw_docs    = bundle.get("canonical_documents", [])
        raw_structs = bundle.get("canonical_structured_records", [])
    else:
        raw_docs, raw_structs = [], []

    source_ledger  = _read(ledger_path,  [])
    duplicate_map  = _read(dup_path,     [])
    quality_report = _read(quality_path, {})

    # ── filter documents ──────────────────────────────────────────────────────
    allowed_statuses = {"usable", "usable_with_warnings"}
    if include_partial:
        allowed_statuses.add("partial")

    skipped_dup      = 0
    skipped_unusable = 0
    passed_docs: list[dict] = []

    for doc in raw_docs:
        dup_status = doc.get("duplicate_status") or {}
        if dup_status.get("is_duplicate") is True:
            skipped_dup += 1
            continue
        q_status = doc.get("quality_status", "usable")
        if q_status not in allowed_statuses:
            skipped_unusable += 1
            continue
        passed_docs.append(doc)

    return {
        "documents":          passed_docs,
        "structured_records": raw_structs if isinstance(raw_structs, list) else [],
        "source_ledger":      source_ledger if isinstance(source_ledger, list) else [],
        "duplicate_map":      duplicate_map if isinstance(duplicate_map, list) else [],
        "quality_report":     quality_report if isinstance(quality_report, dict) else {},
        "stats": {
            "total_docs_raw":          len(raw_docs),
            "docs_skipped_duplicate":  skipped_dup,
            "docs_skipped_unusable":   skipped_unusable,
            "docs_passed":             len(passed_docs),
            "structured_records":      len(raw_structs) if isinstance(raw_structs, list) else 0,
        },
    }
