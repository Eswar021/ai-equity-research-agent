"""
intelligence_layer/final_synthesis_layer/final_input_loader.py — Layer 10

Loads all inputs needed for final synthesis:
  - Layer 9: scorecards, assessments, risk_flags, disagreements, quality_report
  - Layer 8: evidence_cards, thesis_cards
  - Layer 5: market_view, opportunity_hypotheses
  - Layer 6: selected_research_targets
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer9_dir: Path, layer8_dir: Path, layer5_dir: Path, layer6_dir: Path) -> dict:
    layer9_dir = Path(layer9_dir)
    layer8_dir = Path(layer8_dir)
    layer5_dir = Path(layer5_dir)
    layer6_dir = Path(layer6_dir)

    inputs: dict = {}

    # ── Layer 9 outputs ───────────────────────────────────────────────────────
    inputs["target_scorecards"]       = _load_list(layer9_dir / "target_specialist_scorecards.json")
    inputs["specialist_assessments"]  = _load_list(layer9_dir / "specialist_assessments.json")
    inputs["risk_flags"]              = _load_list(layer9_dir / "risk_flags.json")
    inputs["agent_disagreements"]     = _load_list(layer9_dir / "agent_disagreements.json")
    inputs["agent_quality_report"]    = _load_dict(layer9_dir / "agent_quality_report.json")
    inputs["layer9_manifest"]         = _load_dict(layer9_dir / "layer9_manifest.json")

    # research_run_id from L9 manifest
    inputs["research_run_id"] = inputs["layer9_manifest"].get(
        "research_run_id", "RUN_UNKNOWN"
    )

    # ── Layer 8 outputs ───────────────────────────────────────────────────────
    inputs["evidence_cards"]  = _load_list(layer8_dir / "evidence_cards.json")
    inputs["thesis_cards"]    = _load_list(layer8_dir / "thesis_cards.json")

    # ── Layer 5 outputs ───────────────────────────────────────────────────────
    inputs["market_view"]              = _load_dict(layer5_dir / "market_view.json")
    inputs["opportunity_hypotheses"]   = _load_list(layer5_dir / "opportunity_hypotheses.json")

    # ── Layer 6 outputs ───────────────────────────────────────────────────────
    inputs["selected_research_targets"] = _load_list(layer6_dir / "selected_research_targets.json")

    # ── Derived indexes ───────────────────────────────────────────────────────
    inputs["assessments_by_target"] = _index_by(inputs["specialist_assessments"], "target_id")
    inputs["risk_flags_by_target"]  = _index_by(inputs["risk_flags"],             "target_id")
    inputs["disagreements_by_target"] = _index_by(inputs["agent_disagreements"],  "target_id")
    inputs["evidence_by_target"]    = _index_by(inputs["evidence_cards"],         "target_id")
    inputs["thesis_by_target"]      = {
        tc["target_id"]: tc
        for tc in inputs["thesis_cards"]
        if isinstance(tc, dict) and "target_id" in tc
    }
    inputs["opportunities_by_id"]   = {
        h["opportunity_id"]: h
        for h in inputs["opportunity_hypotheses"]
        if isinstance(h, dict) and "opportunity_id" in h
    }

    return inputs


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _index_by(items: list, key: str) -> dict[str, list]:
    index: dict[str, list] = {}
    for item in items:
        if isinstance(item, dict):
            k = item.get(key)
            if k:
                index.setdefault(k, []).append(item)
    return index
