"""
intelligence_layer/canonical_intelligence_extraction/intelligence_bundle_builder.py — Layer 3

Assembles and writes the final Layer 3 output bundle.

Output files (design doc output folder spec):
    output/{date}/layer3/
    ├── intelligence_bundle.json         ← combined view (Layer 4/5/6/8 primary input)
    ├── entity_registry.json
    ├── fact_cards.json
    ├── claim_cards.json
    ├── event_cards.json
    ├── theme_cards.json
    ├── market_signal_cards.json
    ├── unresolved_entities.json
    ├── object_link_map.json
    ├── extraction_quality_report.json
    ├── quarantine.json                  ← written by quarantine_writer
    └── layer3_manifest.json

Design doc: docs/system_design_docs/layer_3.md §25 intelligence_bundle_builder.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import LAYER3_DIR

_IST = timezone(timedelta(hours=5, minutes=30))


def build_extraction_quality_report(
    docs_processed:      int,
    structs_processed:   int,
    docs_skipped_dup:    int,
    docs_skipped_quality: int,
    llm_docs_processed:  int,
    llm_failed:          int,
    entities:            list[dict],
    facts:               list[dict],
    claims:              list[dict],
    events:              list[dict],
    themes:              list[dict],
    signals:             list[dict],
    quarantine_count:    int,
    precheck_warnings:   list[dict],
    contradiction_hints: list[dict],
) -> dict:
    all_confs = [
        o.get("confidence", 0.0)
        for o in entities + facts + claims + events + themes + signals
        if o.get("confidence") is not None
    ]
    avg_conf = round(sum(all_confs) / len(all_confs), 3) if all_confs else 0.0

    return {
        "documents_processed":          docs_processed,
        "structured_records_processed": structs_processed,
        "documents_skipped_duplicates": docs_skipped_dup,
        "documents_skipped_low_quality": docs_skipped_quality,
        "llm_documents_processed":      llm_docs_processed,
        "llm_extraction_failures":      llm_failed,
        "rule_based_records_processed": structs_processed,
        "entities_extracted":           len(entities),
        "facts_extracted":              len(facts),
        "claims_extracted":             len(claims),
        "events_extracted":             len(events),
        "themes_extracted":             len(themes),
        "market_signals_extracted":     len(signals),
        "quarantined_objects":          quarantine_count,
        "precheck_warnings":            len(precheck_warnings),
        "contradiction_hints":          len(contradiction_hints),
        "average_confidence":           avg_conf,
    }


def write_bundle(
    entities:            list[dict],
    facts:               list[dict],
    claims:              list[dict],
    events:              list[dict],
    themes:              list[dict],
    signals:             list[dict],
    unresolved_entities: list[dict],
    object_link_map:     list[dict],
    contradiction_hints: list[dict],
    quality_report:      dict,
    layer3_dir:          Path = LAYER3_DIR,
) -> dict:
    """
    Write all Layer 3 output files.

    Returns layer3_manifest dict with all output paths.
    """
    now     = datetime.now(_IST)
    now_str = now.isoformat()
    layer3_dir.mkdir(parents=True, exist_ok=True)

    def _write(filename: str, data) -> Path:
        p = layer3_dir / filename
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return p

    entity_file  = _write("entity_registry.json",        entities)
    fact_file    = _write("fact_cards.json",              facts)
    claim_file   = _write("claim_cards.json",             claims)
    event_file   = _write("event_cards.json",             events)
    theme_file   = _write("theme_cards.json",             themes)
    signal_file  = _write("market_signal_cards.json",     signals)
    unres_file   = _write("unresolved_entities.json",     unresolved_entities)
    link_file    = _write("object_link_map.json",         object_link_map)
    contra_file  = _write("contradiction_hints.json",     contradiction_hints)
    qual_file    = _write("extraction_quality_report.json", quality_report)

    # Combined intelligence bundle (Layer 4/5/6/8 primary input)
    bundle = {
        "layer":                              "L3_canonical_intelligence_extraction",
        "created_at":                         now_str,
        "total_entities":                     len(entities),
        "total_facts":                        len(facts),
        "total_claims":                       len(claims),
        "total_events":                       len(events),
        "total_themes":                       len(themes),
        "total_market_signals":               len(signals),
        "entity_registry":                    entities,
        "fact_cards":                         facts,
        "claim_cards":                        claims,
        "event_cards":                        events,
        "theme_cards":                        themes,
        "market_signal_cards":                signals,
        "object_link_map":                    object_link_map,
        "quality_summary":                    quality_report,
    }
    bundle_file = _write("intelligence_bundle.json", bundle)

    # Manifest
    manifest = {
        "layer":                              "L3_canonical_intelligence_extraction",
        "status":                             "success",
        "created_at":                         now_str,
        "intelligence_bundle_path":           str(bundle_file),
        "entity_registry_path":               str(entity_file),
        "fact_cards_path":                    str(fact_file),
        "claim_cards_path":                   str(claim_file),
        "event_cards_path":                   str(event_file),
        "theme_cards_path":                   str(theme_file),
        "market_signal_cards_path":           str(signal_file),
        "unresolved_entities_path":           str(unres_file),
        "object_link_map_path":               str(link_file),
        "contradiction_hints_path":           str(contra_file),
        "extraction_quality_report_path":     str(qual_file),
        "entity_count":                       len(entities),
        "fact_count":                         len(facts),
        "claim_count":                        len(claims),
        "event_count":                        len(events),
        "theme_count":                        len(themes),
        "market_signal_count":                len(signals),
    }
    _write("layer3_manifest.json", manifest)
    return manifest
