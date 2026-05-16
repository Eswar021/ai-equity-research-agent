"""
intelligence_layer/specialist_analysis/agent_input_loader.py — Layer 9

Loads all Layer 8 outputs and groups them for agent task creation.
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer8_dir: Path) -> dict:
    """
    Returns:
    {
        "agent_context_packets":  list,
        "target_evidence_packs":  list,
        "evidence_cards":         list,
        "numeric_features":       list,
        "thesis_cards":           list,
        "evidence_gaps":          list,
        "packets_by_target":      {target_id: {agent_type: packet}},
        "evidence_by_target":     {target_id: list[card]},
        "features_by_target":     {target_id: {feature_group: dict}},
        "thesis_by_target":       {target_id: dict},
        "gaps_by_target":         {target_id: list},
        "packs_by_target":        {target_id: dict},
        "research_run_id":        str,
        "load_warnings":          list[str],
    }
    """
    layer8_dir = Path(layer8_dir)
    warnings: list[str] = []

    packets    = _load(layer8_dir / "agent_context_packets.json",   warnings, "agent_context_packets")  or []
    packs      = _load(layer8_dir / "target_evidence_packs.json",   warnings, "target_evidence_packs")   or []
    cards      = _load(layer8_dir / "evidence_cards.json",           warnings, "evidence_cards")           or []
    features   = _load(layer8_dir / "numeric_features.json",         warnings, "numeric_features")         or []
    thesis     = _load(layer8_dir / "thesis_cards.json",             warnings, "thesis_cards")             or []
    gaps       = _load(layer8_dir / "evidence_gap_report.json",      warnings, "evidence_gap_report")      or []
    manifest   = _load(layer8_dir / "layer8_manifest.json",          warnings, "layer8_manifest")          or {}

    # Group packets by target_id → agent_type
    packets_by_target: dict[str, dict[str, dict]] = {}
    for pkt in packets:
        tid  = pkt.get("target_id", "")
        atype = pkt.get("agent_type", "")
        packets_by_target.setdefault(tid, {})[atype] = pkt

    # Group evidence cards by target_id
    evidence_by_target: dict[str, list[dict]] = {}
    for card in cards:
        tid = card.get("target_id", "")
        evidence_by_target.setdefault(tid, []).append(card)

    # Group feature groups by target_id → feature_group name
    features_by_target: dict[str, dict[str, dict]] = {}
    for fg in features:
        tid = fg.get("target_id", "")
        grp = fg.get("feature_group", fg.get("feature_group_id", ""))
        features_by_target.setdefault(tid, {})[grp] = fg

    # Thesis by target_id
    thesis_by_target: dict[str, dict] = {t["target_id"]: t for t in thesis if "target_id" in t}

    # Gaps by target_id
    gaps_by_target: dict[str, list[dict]] = {}
    for g in gaps:
        tid = g.get("target_id", "")
        gaps_by_target.setdefault(tid, []).append(g)

    # Evidence packs by target_id
    packs_by_target: dict[str, dict] = {p["target_id"]: p for p in packs if "target_id" in p}

    return {
        "agent_context_packets":  packets,
        "target_evidence_packs":  packs,
        "evidence_cards":         cards,
        "numeric_features":       features,
        "thesis_cards":           thesis,
        "evidence_gaps":          gaps,
        "packets_by_target":      packets_by_target,
        "evidence_by_target":     evidence_by_target,
        "features_by_target":     features_by_target,
        "thesis_by_target":       thesis_by_target,
        "gaps_by_target":         gaps_by_target,
        "packs_by_target":        packs_by_target,
        "research_run_id":        manifest.get("research_run_id", ""),
        "load_warnings":          warnings,
    }


def _load(path: Path, warnings: list, label: str):
    if not path.exists():
        warnings.append(f"Missing: {label} ({path.name})")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Parse error {label}: {exc}")
        return None
