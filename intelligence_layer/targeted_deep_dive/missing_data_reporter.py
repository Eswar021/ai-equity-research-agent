"""
intelligence_layer/targeted_deep_dive/missing_data_reporter.py — Layer 7

Creates explicit missing-data records for failed or skipped tasks.
Downstream layers (L8/L9) use these to know what evidence is absent.

Design doc: docs/system_design_docs/layer_7.md §10.12 missing_data_reporter.py
"""

from __future__ import annotations

_MODULE_IMPACT: dict[str, str] = {
    "market_data":        "No current price or market context",
    "price_history":      "No historical price/return data",
    "screener_in":        "No fundamentals (revenue, ROE, debt, growth metrics)",
    "peer_comparison":    "No peer valuation benchmark",
    "analyst_estimates":  "No consensus targets or earnings estimates",
    "exchange_filings":   "No official corporate announcements",
    "filing_docs":        "Management commentary gap — no concall transcripts",
    "corporate_actions":  "No dividend / buyback / split context",
}

_MODULE_NEXT_ACTION: dict[str, str] = {
    "market_data":        "retry or use cached price",
    "price_history":      "retry with smaller period",
    "screener_in":        "try alternate URL or mark gap for L8",
    "peer_comparison":    "mark gap for L8",
    "analyst_estimates":  "mark gap for L8; analyst data may be unavailable",
    "exchange_filings":   "retry NSE session; mark gap for L8",
    "filing_docs":        "no transcript available; lower conviction in L9",
    "corporate_actions":  "mark gap; use exchange_filings as fallback",
}


def report_missing(ctx: dict, task_results: list[dict], skipped: list[dict]) -> list[dict]:
    """Return missing-data items for one target."""
    missing = []

    for r in task_results:
        if r["status"] == "failed":
            module = r["module"]
            missing.append({
                "target_id":        ctx["target_id"],
                "target_name":      ctx["target_name"],
                "module":           module,
                "missing_data_type": module,
                "reason":           r.get("error", "unknown error"),
                "impact":           _MODULE_IMPACT.get(module, f"{module} data unavailable"),
                "next_action":      _MODULE_NEXT_ACTION.get(module, "retry or mark gap"),
            })

    for s in skipped:
        module = s["module"]
        missing.append({
            "target_id":        ctx["target_id"],
            "target_name":      ctx["target_name"],
            "module":           module,
            "missing_data_type": module,
            "reason":           f"skipped: {s['reason']}",
            "impact":           _MODULE_IMPACT.get(module, f"{module} data unavailable"),
            "next_action":      "add to collector registry to enable",
        })

    return missing


def report_all_missing(
    contexts: list[dict],
    all_task_results: dict[str, list[dict]],
    all_skipped: dict[str, list[dict]],
) -> list[dict]:
    all_missing = []
    for ctx in contexts:
        tid = ctx["target_id"]
        all_missing.extend(
            report_missing(ctx, all_task_results.get(tid, []), all_skipped.get(tid, []))
        )
    return all_missing
