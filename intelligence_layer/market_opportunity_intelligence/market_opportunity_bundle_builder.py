"""
intelligence_layer/market_opportunity_intelligence/market_opportunity_bundle_builder.py — Layer 5

Pure Python bundle writer. Takes all Layer 5 outputs and writes individual JSON files
plus a manifest to the layer5 output directory.

Design doc: docs/system_design_docs/layer_5.md §14 market_opportunity_bundle_builder.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))


def build_and_write(
    layer5_dir: Path,
    run_id: str,
    market_view: dict,
    sector_theme_views: list[dict],
    event_impact_views: list[dict],
    opportunity_hypotheses: list[dict],
    cross_domain_chains: list[dict],
    time_horizon_views: list[dict],
    hypothesis_strength_scores: list[dict],
    guardrail_results: list[dict],
    signal_groups: list[dict],
    load_summary: dict,
) -> dict:
    """
    Write all Layer 5 artifacts to layer5_dir.
    Returns manifest dict.
    """
    layer5_dir = Path(layer5_dir)
    layer5_dir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(_IST).isoformat()

    # ── Write individual files ────────────────────────────────────────────────
    _write(layer5_dir / "market_view.json",              market_view)
    _write(layer5_dir / "sector_theme_views.json",       sector_theme_views)
    _write(layer5_dir / "event_impact_views.json",       event_impact_views)
    _write(layer5_dir / "opportunity_hypotheses.json",   opportunity_hypotheses)
    _write(layer5_dir / "cross_domain_chains.json",      cross_domain_chains)
    _write(layer5_dir / "time_horizon_views.json",       time_horizon_views)
    _write(layer5_dir / "hypothesis_strength_scores.json", hypothesis_strength_scores)
    _write(layer5_dir / "guardrail_results.json",        guardrail_results)
    _write(layer5_dir / "signal_groups.json",            signal_groups)

    # ── Quality report ────────────────────────────────────────────────────────
    gr_pass       = sum(1 for r in guardrail_results if r.get("status") == "pass")
    gr_downgraded = sum(1 for r in guardrail_results if r.get("status") == "downgraded")
    gr_quarantine = sum(1 for r in guardrail_results if r.get("status") == "quarantined")
    gr_theme_only = sum(1 for r in guardrail_results if r.get("status") == "theme_only")
    sent_to_l6    = sum(1 for s in hypothesis_strength_scores if s.get("send_to_layer6"))
    rejected      = len(hypothesis_strength_scores) - sent_to_l6

    confs = [h.get("confidence", 0) for h in opportunity_hypotheses]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0

    quality_report = {
        "research_run_id":                run_id,
        "layer":                          "L5_market_opportunity_intelligence",
        "created_at":                     now_str,
        "input_summary":                  load_summary,
        "signal_groups_built":            len(signal_groups),
        "market_views_created":           1 if market_view else 0,
        "sector_theme_views_created":     len(sector_theme_views),
        "event_impact_views_created":     len(event_impact_views),
        "opportunity_hypotheses_created": len(opportunity_hypotheses),
        "cross_domain_chains_created":    len(cross_domain_chains),
        "time_horizon_views_created":     len(time_horizon_views),
        "hypotheses_sent_to_layer6":      sent_to_l6,
        "hypotheses_rejected":            rejected,
        "guardrail_pass":                 gr_pass,
        "guardrail_downgraded":           gr_downgraded,
        "guardrail_quarantined":          gr_quarantine,
        "guardrail_theme_only":           gr_theme_only,
        "average_hypothesis_confidence":  avg_conf,
    }
    _write(layer5_dir / "layer5_quality_report.json", quality_report)

    # ── Manifest ──────────────────────────────────────────────────────────────
    manifest = {
        "research_run_id":               run_id,
        "layer":                         "L5_market_opportunity_intelligence",
        "created_at":                    now_str,
        "status":                        "success",
        "market_view_path":              str(layer5_dir / "market_view.json"),
        "sector_theme_views_path":       str(layer5_dir / "sector_theme_views.json"),
        "event_impact_views_path":       str(layer5_dir / "event_impact_views.json"),
        "opportunity_hypotheses_path":   str(layer5_dir / "opportunity_hypotheses.json"),
        "cross_domain_chains_path":      str(layer5_dir / "cross_domain_chains.json"),
        "time_horizon_views_path":       str(layer5_dir / "time_horizon_views.json"),
        "hypothesis_strength_scores_path": str(layer5_dir / "hypothesis_strength_scores.json"),
        "guardrail_results_path":        str(layer5_dir / "guardrail_results.json"),
        "signal_groups_path":            str(layer5_dir / "signal_groups.json"),
        "quality_report_path":           str(layer5_dir / "layer5_quality_report.json"),
        "quality_summary": {
            "signal_groups":      len(signal_groups),
            "hypotheses_created": len(opportunity_hypotheses),
            "hypotheses_to_l6":   sent_to_l6,
            "avg_confidence":     avg_conf,
        },
    }
    _write(layer5_dir / "layer5_manifest.json", manifest)

    return manifest


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
