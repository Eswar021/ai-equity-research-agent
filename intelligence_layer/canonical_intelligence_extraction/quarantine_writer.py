"""
intelligence_layer/canonical_intelligence_extraction/quarantine_writer.py — Layer 3

Accumulates and writes invalid or unsupported extraction outputs to quarantine.json.
Called by schema_validator and source_ref_validator when objects fail validation.

Design doc: docs/system_design_docs/layer_3.md §24 quarantine_writer.py
"""

from __future__ import annotations
import json
from pathlib import Path


class QuarantineWriter:
    """Accumulates quarantine items during a Layer 3 run and writes them at the end."""

    def __init__(self):
        self._items: list[dict] = []

    def add(
        self,
        object_type:     str,
        object_id:       str,
        reason:          str,
        raw_object:      dict | None = None,
    ) -> None:
        self._items.append({
            "object_type": object_type,
            "object_id":   object_id,
            "reason":      reason,
            "raw_object":  raw_object or {},
        })

    def add_many(self, invalid_objects: list[dict]) -> None:
        """Add a list of invalid objects from schema_validator or source_ref_validator."""
        for item in invalid_objects:
            obj      = item.get("object", item)
            obj_type = item.get("object_type", "unknown")
            errors   = item.get("errors", [])
            # Try to find the ID field
            obj_id = (
                obj.get("entity_id") or obj.get("fact_id") or obj.get("claim_id")
                or obj.get("event_id") or obj.get("theme_id") or obj.get("signal_id")
                or "unknown"
            )
            reason = "; ".join(errors) if errors else obj.get("validation_error", "schema_invalid")
            self.add(obj_type, obj_id, reason, obj)

    def count(self) -> int:
        return len(self._items)

    def write(self, layer3_dir: Path) -> Path:
        layer3_dir.mkdir(parents=True, exist_ok=True)
        out = layer3_dir / "quarantine.json"
        out.write_text(json.dumps(self._items, ensure_ascii=False, indent=2))
        return out
