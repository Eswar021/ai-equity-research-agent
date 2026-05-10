"""
intelligence_layer/memory_qualification/intelligence_input_loader.py — Layer 4

Loads Layer 3 intelligence outputs from the dated output directory.
Returns objects grouped by type for downstream qualification.

Design doc: docs/system_design_docs/layer_4.md §2 intelligence_input_loader.py
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer3_dir: str | Path) -> dict:
    """
    Load all Layer 3 intelligence objects from a dated layer3/ directory.

    Returns:
        {
            "entities":       list[dict],
            "facts":          list[dict],
            "claims":         list[dict],
            "events":         list[dict],
            "themes":         list[dict],
            "market_signals": list[dict],
            "object_links":   list[dict],
            "load_summary":   {file: count, ...}
        }
    """
    d = Path(layer3_dir)
    file_map = {
        "entities":       "entity_registry.json",
        "facts":          "fact_cards.json",
        "claims":         "claim_cards.json",
        "events":         "event_cards.json",
        "themes":         "theme_cards.json",
        "market_signals": "market_signal_cards.json",
        "object_links":   "object_link_map.json",
    }
    result: dict = {"load_summary": {}}
    for key, fname in file_map.items():
        path = d / fname
        if path.exists():
            raw = json.loads(path.read_text())
            # Most files are lists directly; entity_registry may be dict-of-lists
            if isinstance(raw, list):
                result[key] = raw
            elif isinstance(raw, dict):
                # entity_registry.json is {"entities": [...], ...}
                if key == "entities" and "entities" in raw:
                    result[key] = raw["entities"]
                elif key == "object_links" and "links" in raw:
                    result[key] = raw["links"]
                else:
                    # flatten any first list value
                    first = next((v for v in raw.values() if isinstance(v, list)), [])
                    result[key] = first
            else:
                result[key] = []
            result["load_summary"][fname] = len(result[key])
        else:
            result[key] = []
            result["load_summary"][fname] = 0
    return result
