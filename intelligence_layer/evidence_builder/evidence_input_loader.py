"""
intelligence_layer/evidence_builder/evidence_input_loader.py — Layer 8

Loads all upstream inputs Layer 8 needs:
  - L5: opportunity_hypotheses, market_view
  - L6: selected_research_targets
  - L7: target_raw_bundles, coverage_report, missing_data_report, layer7_manifest
  - L7/targets/: per-target raw JSON files (market_data, price_history, screener_in,
                  peer_comparison, analyst_estimates, exchange_filings)

ADR-L8-001: reads L7 raw JSON directly — no L2-targeted or L3-targeted pass.
"""

from __future__ import annotations
import json
from pathlib import Path


def load(layer5_dir: Path, layer6_dir: Path, layer7_dir: Path) -> dict:
    """
    Returns:
    {
        "opportunity_hypotheses": list,
        "market_view": dict,
        "selected_targets": list,
        "coverage_report": list,
        "missing_data_report": list,
        "target_files": {
            target_id: {
                "market_data": dict | None,
                "price_history": dict | None,
                "screener_in": dict | None,
                "peer_comparison": dict | None,
                "analyst_estimates": dict | None,
                "exchange_filings": dict | None,
                "target_dir": str,
            }
        },
        "load_warnings": list[str],
    }
    """
    layer5_dir = Path(layer5_dir)
    layer6_dir = Path(layer6_dir)
    layer7_dir = Path(layer7_dir)

    warnings: list[str] = []

    opportunity_hypotheses = _load_json(layer5_dir / "opportunity_hypotheses.json", warnings, "L5 opportunity_hypotheses") or []
    market_view            = _load_json(layer5_dir / "market_view.json",            warnings, "L5 market_view")            or {}
    selected_targets       = _load_json(layer6_dir / "selected_research_targets.json", warnings, "L6 selected_research_targets") or []
    coverage_report        = _load_json(layer7_dir / "coverage_report.json",         warnings, "L7 coverage_report")         or []
    missing_data_report    = _load_json(layer7_dir / "missing_data_report.json",      warnings, "L7 missing_data_report")      or []
    manifest               = _load_json(layer7_dir / "layer7_manifest.json",          warnings, "L7 manifest")                 or {}

    # selected_targets may be a list directly or wrapped in a dict
    if isinstance(selected_targets, dict):
        selected_targets = selected_targets.get("selected_targets", [])

    # Build hypotheses lookup by opportunity_id for fast resolution
    hyp_by_id: dict[str, dict] = {h["opportunity_id"]: h for h in opportunity_hypotheses if "opportunity_id" in h}

    # Build coverage + missing data lookup by target_id
    coverage_by_target: dict[str, dict] = {}
    for item in (coverage_report if isinstance(coverage_report, list) else []):
        tid = item.get("target_id")
        if tid:
            coverage_by_target[tid] = item

    missing_by_target: dict[str, list] = {}
    for item in (missing_data_report if isinstance(missing_data_report, list) else []):
        tid = item.get("target_id")
        if tid:
            missing_by_target.setdefault(tid, []).append(item)

    # Load per-target raw files from layer7/targets/
    targets_dir = layer7_dir / "targets"
    target_files: dict[str, dict] = {}

    for target in selected_targets:
        tid = target.get("target_id", "")
        if not tid:
            continue

        # Find the target directory (named {tid}_{slug})
        t_dir = _find_target_dir(targets_dir, tid)
        if t_dir is None:
            warnings.append(f"No L7 target dir found for {tid}")
            target_files[tid] = _empty_target_files(tid)
            continue

        target_files[tid] = {
            "target_dir":        str(t_dir),
            "market_data":       _load_json(t_dir / "market_data.json",       warnings, f"{tid}/market_data"),
            "price_history":     _load_json(t_dir / "price_history.json",      warnings, f"{tid}/price_history"),
            "screener_in":       _load_json(t_dir / "screener_in.json",        warnings, f"{tid}/screener_in"),
            "peer_comparison":   _load_json(t_dir / "peer_comparison.json",    warnings, f"{tid}/peer_comparison"),
            "analyst_estimates": _load_json(t_dir / "analyst_estimates.json",  warnings, f"{tid}/analyst_estimates"),
            "exchange_filings":  _load_json(t_dir / "exchange_filings.json",   warnings, f"{tid}/exchange_filings"),
        }

    return {
        "opportunity_hypotheses": opportunity_hypotheses,
        "hyp_by_id":              hyp_by_id,
        "market_view":            market_view,
        "selected_targets":       selected_targets,
        "coverage_by_target":     coverage_by_target,
        "missing_by_target":      missing_by_target,
        "target_files":           target_files,
        "research_run_id":        manifest.get("research_run_id", ""),
        "load_warnings":          warnings,
    }


def _load_json(path: Path, warnings: list, label: str):
    if not path.exists():
        warnings.append(f"Missing file: {label} ({path})")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Failed to parse {label}: {exc}")
        return None


def _find_target_dir(targets_dir: Path, target_id: str) -> Path | None:
    if not targets_dir.exists():
        return None
    for d in targets_dir.iterdir():
        if d.is_dir() and d.name.startswith(target_id):
            return d
    return None


def _empty_target_files(target_id: str) -> dict:
    return {
        "target_dir":        None,
        "market_data":       None,
        "price_history":     None,
        "screener_in":       None,
        "peer_comparison":   None,
        "analyst_estimates": None,
        "exchange_filings":  None,
    }
