"""
intelligence_layer/specialist_analysis/confidence_calibrator.py — Layer 9

Adjusts assessment confidence based on evidence quality signals from L8.
Operates on completed assessments — does not re-run LLM.
"""

from __future__ import annotations


def calibrate_all(task_results: list[dict], inputs: dict) -> list[dict]:
    """Adjust confidence on each assessment in-place. Returns same list."""
    packs_by_target = inputs.get("packs_by_target", {})
    gaps_by_target  = inputs.get("gaps_by_target", {})

    for result in task_results:
        if result["status"] == "failed":
            continue
        assessment = result.get("assessment", {})
        tid = assessment.get("target_id", "")

        pack = packs_by_target.get(tid, {})
        gaps = gaps_by_target.get(tid, [])

        original = assessment.get("confidence", 0.5)
        calibrated, reasons = _calibrate(original, pack, gaps, assessment)

        assessment["original_confidence"]  = original
        assessment["confidence"]           = calibrated
        assessment["calibration_reasons"]  = reasons

    return task_results


def _calibrate(orig: float, pack: dict, gaps: list[dict], assessment: dict):
    reasons: list[str] = []
    adj = 0.0

    # Evidence coverage quality
    coverage_pct = pack.get("coverage_pct", 1.0)
    if coverage_pct < 0.5:
        adj -= 0.08
        reasons.append("Low data coverage (<50%)")
    elif coverage_pct < 0.7:
        adj -= 0.04
        reasons.append("Partial data coverage")

    # High severity gaps
    high_gaps = sum(1 for g in gaps if g.get("severity") == "high")
    if high_gaps >= 3:
        adj -= 0.08
        reasons.append(f"{high_gaps} high-severity data gaps")
    elif high_gaps >= 1:
        adj -= 0.04
        reasons.append(f"{high_gaps} high-severity gap(s)")

    # Average evidence strength
    avg_strength = pack.get("evidence_summary", {}).get("avg_strength_score") or 0.8
    if avg_strength < 0.6:
        adj -= 0.05
        reasons.append(f"Evidence quality below threshold (avg={avg_strength:.2f})")
    elif avg_strength >= 0.85:
        adj += 0.03
        reasons.append(f"Evidence quality strong (avg={avg_strength:.2f})")

    # Agent-level: if the agent itself flagged data gaps
    if len(assessment.get("data_gaps", [])) >= 3:
        adj -= 0.04
        reasons.append("Agent flagged multiple data gaps")

    calibrated = round(max(0.05, min(0.95, orig + adj)), 3)
    if not reasons:
        reasons.append("No calibration adjustments needed")
    return calibrated, reasons
