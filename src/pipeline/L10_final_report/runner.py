"""
L10 Final Report — composite scoring, narrative synthesis, daily report, watchlist + memory.

Reads:
    output/{date}/run_manifest.json          → layer_10 config
    output/{date}/L9/scorecards.json         → 4 specialist assessments per target

Writes:
    output/{date}/L10/final_report.md        → Markdown daily research report (consumed by humans)
    output/{date}/L10/watchlist_actions.json → machine-readable watchlist decisions
    output/{date}/L10/summary.json           → counts, scores, elapsed time
    output/{date}/L10/llm_calls.jsonl        → full prompt+response per LLM call
    db/memory/watch_memory.jsonl             → target-level investment decision facts (side-effect)

LLM: yes — 2 calls per target (synthesis + scenarios).
     Provider + model from manifest layer_10 config.
     Phase 1: synthesis for all targets in parallel via ThreadPoolExecutor.
     Phase 2: scenarios for all targets in parallel — receives synthesis as context.

Module execution order:
    1. Load manifest → layer_10 config; load L9/scorecards.json
    2. Compute composite score + market_alignment for each target (rule-based, no LLM)
    3. Build LLM + synthesis_chain + scenarios_chain
    4. Phase 1: run synthesis for all targets in parallel
    5. Phase 2: run scenarios for all targets in parallel
    6. Assemble report_items (ranked by composite score)
    7. Write final_report.md, watchlist_actions.json, summary.json
    8. Append qualifying targets to db/memory/watch_memory.jsonl

Usage:
    python -m src.pipeline.L10_final_report.runner              # today
    python -m src.pipeline.L10_final_report.runner --date 2026-05-17
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, PROJECT_ROOT, load_manifest, output_dir, today
from src.llm.client import make_llm
from src.pipeline.L10_final_report.agents import (
    SYNTHESIS_PROMPT,
    SCENARIOS_PROMPT,
    InvestmentNarrative,
    InvestmentScenarios,
    run_synthesis,
    run_scenarios,
)

_DB_MEMORY = PROJECT_ROOT / "db" / "memory" / "watch_memory.jsonl"

_STATUS_RE = re.compile(r"\|\s*Status:\s*(not_triggered|watch|imminent)", re.IGNORECASE)

_STATUS_BADGE = {
    "not_triggered": "✅",
    "watch":         "⚠️",
    "imminent":      "🔴",
}


# ---------------------------------------------------------------------------
# Rule-based scoring
# ---------------------------------------------------------------------------

def _market_alignment(sc: dict, cfg: dict) -> int:
    macro     = sc.get("macro_context", {})
    regime    = macro.get("regime", "uncertain")
    strength  = sc.get("strength", "medium")
    fii_net   = macro.get("fii_net_cr", 0) or 0
    threshold = cfg.get("fii_adj_threshold", 500)

    base = cfg["regime_base_score"].get(regime, 50)
    adj  = cfg["thesis_strength_adj"].get(strength, 0)
    fii  = 10 if fii_net > threshold else (-10 if fii_net < -threshold else 0)
    return max(0, min(100, base + adj + fii))


def _composite(sc: dict, cfg: dict) -> tuple[int, int]:
    w  = cfg["weights"]
    f  = sc.get("fundamental", {}).get("score", 50)
    v  = sc.get("valuation", {}).get("score", 50)
    r  = sc.get("risk", {}).get("score", 50)
    t  = sc.get("thesis_validation", {}).get("score", 50)
    ma = _market_alignment(sc, cfg)
    raw = (
        w["fundamental"]      * f
        + w["valuation"]      * v
        + w["thesis"]         * t
        + w["risk_inverted"]  * (100 - r)
        + w["market_alignment"] * ma
    )
    return round(raw), ma


def _recommendation(sc: dict, composite: int, cfg: dict) -> str:
    thesis_verdict = sc.get("thesis_validation", {}).get("verdict", "")
    if thesis_verdict == "contradicted":
        return "avoid"
    if composite >= cfg["high_conviction_threshold"]:
        return "strong_buy"
    if composite >= cfg["buy_threshold"]:
        return "buy"
    if thesis_verdict == "insufficient_data" or composite >= cfg["watch_threshold"]:
        return "watch"
    return "avoid"


# ---------------------------------------------------------------------------
# Markdown report helpers
# ---------------------------------------------------------------------------

def _fii_label(fii_net: float, threshold: float) -> str:
    if fii_net > threshold:
        return f"FII +{fii_net:,.0f}cr (tailwind)"
    if fii_net < -threshold:
        return f"FII {fii_net:,.0f}cr (headwind)"
    return f"FII {fii_net:+,.0f}cr (neutral)"


def _parse_status(check_item: str) -> str:
    m = _STATUS_RE.search(check_item)
    return m.group(1).lower() if m else "unknown"


def _render_invalidation(invalidation_check: list[str]) -> str:
    lines = []
    for item in invalidation_check:
        status = _parse_status(item)
        badge  = _STATUS_BADGE.get(status, "❓")
        lines.append(f"- {badge} {item}")
    return "\n".join(lines) or "  (none)"


def _render_bullet(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) or "  (none)"


def _rec_display(rec: str) -> str:
    return rec.upper().replace("_", " ")


def _build_market_header(macro: dict, fii_threshold: float, run_date: str) -> str:
    regime    = macro.get("regime", "unknown").capitalize()
    fii_net   = macro.get("fii_net_cr", 0) or 0
    dii_net   = macro.get("dii_net_cr", 0) or 0
    nifty_chg = macro.get("nifty_change_pct", 0) or 0
    fii_str   = _fii_label(fii_net, fii_threshold)
    dii_str   = f"DII {dii_net:+,.0f}cr"
    nifty_str = f"Nifty {nifty_chg:+.2f}%"
    return (
        f"# Stock Research Report — {run_date}\n"
        f"**Market:** {regime} | {fii_str} | {dii_str} | {nifty_str}\n"
    )


def _build_summary_table(ranked: list[dict]) -> str:
    rows = ["| Rank | Target | Score | Rec | F | V | R | T | MA | Conviction |",
            "|------|--------|-------|-----|---|---|---|---|----|------------|"]
    for i, item in enumerate(ranked, 1):
        sc   = item["scorecard"]
        rows.append(
            f"| {i} | {sc['target_entity']} | {item['composite_score']} "
            f"| {_rec_display(item['recommendation'])} "
            f"| {sc.get('fundamental', {}).get('score', '?')} "
            f"| {sc.get('valuation', {}).get('score', '?')} "
            f"| {sc.get('risk', {}).get('score', '?')} "
            f"| {sc.get('thesis_validation', {}).get('score', '?')} "
            f"| {item['market_alignment']} "
            f"| {sc.get('thesis_validation', {}).get('conviction_level', '?')} |"
        )
    return "\n".join(rows)


def _build_target_section(rank: int, item: dict) -> str:
    sc         = item["scorecard"]
    synthesis  = item["synthesis"]
    scenarios  = item["scenarios"]
    composite  = item["composite_score"]
    rec        = item["recommendation"]
    ma         = item["market_alignment"]
    thesis     = sc.get("thesis", {})

    f_sc  = sc.get("fundamental", {})
    v_sc  = sc.get("valuation", {})
    r_sc  = sc.get("risk", {})
    t_sc  = sc.get("thesis_validation", {})

    f_finding = (f_sc.get("key_findings") or [""])[0]
    v_finding = (v_sc.get("key_findings") or [""])[0]
    r_finding = (r_sc.get("red_flags") or r_sc.get("key_findings") or [""])[0]
    t_finding = (t_sc.get("key_findings") or [""])[0]

    bull_prob = scenarios.get("probability_bull", "?")
    base_prob = scenarios.get("probability_base", "?")
    bear_prob = scenarios.get("probability_bear", "?")
    bull_px   = scenarios.get("bull_price_target")
    base_px   = scenarios.get("base_price_target")
    bear_px   = scenarios.get("bear_price_target")
    bull_ret  = scenarios.get("bull_return_pct")
    base_ret  = scenarios.get("base_return_pct")
    bear_ret  = scenarios.get("bear_return_pct")
    bull_case = scenarios.get("bull_case", "")
    base_case = scenarios.get("base_case", "")
    bear_case = scenarios.get("bear_case", "")

    def _px(v):
        return f"₹{v:,.0f}" if v is not None else "?"

    def _pct(v):
        if v is None:
            return "?"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}%"

    return (
        f"\n---\n\n"
        f"## {rank}. {sc['target_entity']} — {_rec_display(rec)} (Composite: {composite}/100)\n"
        f"**Thesis:** {thesis.get('hypothesis', '')[:200]}\n"
        f"**Entry Range:** {synthesis.get('entry_price_range', '?')} | "
        f"**Stop:** {synthesis.get('stop_loss_guide', '?')}\n"
        f"**Time Horizon:** {sc.get('time_horizon', '?')} | "
        f"**Conviction:** {t_sc.get('conviction_level', '?')}\n\n"
        f"### Investment Narrative\n{synthesis.get('investment_narrative', '')}\n\n"
        f"### Scenarios\n\n"
        f"| | Bull ({bull_prob}%) | Base ({base_prob}%) | Bear ({bear_prob}%) |\n"
        f"|---|---|---|---|\n"
        f"| **Price Target** | {_px(bull_px)} ({_pct(bull_ret)}) "
        f"| {_px(base_px)} ({_pct(base_ret)}) "
        f"| {_px(bear_px)} ({_pct(bear_ret)}) |\n"
        f"| **Description** | {bull_case} | {base_case} | {bear_case} |\n\n"
        f"### Scorecard Components\n"
        f"- **Fundamental:** {f_sc.get('score', '?')}/100 ({f_sc.get('verdict', '?')}) — {f_finding}\n"
        f"- **Valuation:** {v_sc.get('score', '?')}/100 ({v_sc.get('verdict', '?')}) — {v_finding}\n"
        f"- **Risk:** {r_sc.get('score', '?')}/100 ({r_sc.get('verdict', '?')}) — {r_finding}\n"
        f"- **Thesis:** {t_sc.get('score', '?')}/100 ({t_sc.get('verdict', '?')}) — {t_finding}\n"
        f"- **Market Alignment:** {ma}/100\n\n"
        f"### Invalidation Monitor\n"
        f"{_render_invalidation(t_sc.get('invalidation_check', []))}\n\n"
        f"### Watch For\n"
        f"{_render_bullet(synthesis.get('catalysts', []))}\n"
    )


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _fact_summary(sc: dict, recommendation: str) -> str:
    pd = sc.get("price_data", {})
    prices  = [d["current"] for d in pd.values() if d.get("current")]
    upsides = [d["upside_pct"] for d in pd.values() if d.get("upside_pct")]
    if prices:
        price_str = (
            f"₹{min(prices):,.0f}–{max(prices):,.0f}"
            if len(prices) > 1
            else f"₹{prices[0]:,.0f}"
        )
    else:
        price_str = "N/A"
    upside_str = (
        f"; mean analyst upside {round(sum(upsides)/len(upsides), 1)}%"
        if upsides else ""
    )
    return (
        f"{sc['target_entity']} rated {recommendation} at {price_str}"
        f"{upside_str}; {sc.get('time_horizon', '')} thesis."
    )


def _build_memory_entry(item: dict, run_date: str, run_id: str) -> dict:
    sc         = item["scorecard"]
    thesis     = sc.get("thesis", {})
    resolution = sc.get("resolution", {})
    pd         = sc.get("price_data", {})
    t_sc       = sc.get("thesis_validation", {})
    rec        = item["recommendation"]

    price_at_decision  = {t: d["current"]        for t, d in pd.items() if d.get("current")}
    analyst_target     = {t: d["analyst_target"]  for t, d in pd.items() if d.get("analyst_target")}
    analyst_upside_pct = {t: d["upside_pct"]      for t, d in pd.items() if d.get("upside_pct")}

    invalidating_conditions = thesis.get("invalidating_conditions", [])
    invalidation_statuses   = [_parse_status(c) for c in t_sc.get("invalidation_check", [])]

    beneficiaries       = thesis.get("beneficiaries", [])
    resolution_tickers  = resolution.get("tickers", [])
    triggered_by        = list(dict.fromkeys(
        [sc["target_entity"]] + beneficiaries + resolution_tickers
    ))

    return {
        "memory_type":             "investment_decision",
        "entity":                  sc["target_entity"],
        "tickers":                 resolution_tickers,
        "run_date":                run_date,
        "title":                   f"{sc['target_entity']} — {rec} (score={item['composite_score']})",
        "price_at_decision":       price_at_decision,
        "analyst_target":          analyst_target,
        "analyst_upside_pct":      analyst_upside_pct,
        "composite_score":         item["composite_score"],
        "fundamental_score":       sc.get("fundamental", {}).get("score"),
        "valuation_score":         sc.get("valuation", {}).get("score"),
        "risk_score":              sc.get("risk", {}).get("score"),
        "thesis_score":            sc.get("thesis_validation", {}).get("score"),
        "market_alignment":        item["market_alignment"],
        "recommendation":          rec,
        "time_horizon":            sc.get("time_horizon"),
        "invalidating_conditions": invalidating_conditions,
        "invalidation_statuses":   invalidation_statuses,
        "summary":                 _fact_summary(sc, rec),
        "triggered_by_entities":   triggered_by,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    t_start = time.time()
    date    = run_date or today()

    manifest = load_manifest(date)
    cfg      = manifest["layer_10"]

    scorecards_path = output_dir(date) / "L9" / "scorecards.json"
    if not scorecards_path.exists():
        raise FileNotFoundError(f"L9 output not found: {scorecards_path}")
    l9_data    = json.loads(scorecards_path.read_text())
    scorecards = l9_data["scorecards"]
    if not scorecards:
        raise ValueError("L9 scorecards.json contains no scorecards")

    provider    = cfg.get("provider", "openai")
    model       = cfg.get("model") or None
    max_workers = int(cfg.get("max_workers", 4))

    llm        = make_llm(provider=provider, model=model)
    model_name = getattr(llm, "model_name", None) or model or provider

    out_dir  = output_dir(date) / "L10"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "llm_calls.jsonl"
    lock     = threading.Lock()
    counter  = itertools.count(1)

    def _call_id() -> str:
        return f"L10_{date.replace('-', '')}_{'%04d' % next(counter)}"

    synthesis_chain = SYNTHESIS_PROMPT | llm.with_structured_output(InvestmentNarrative, include_raw=True)
    scenarios_chain = SCENARIOS_PROMPT | llm.with_structured_output(InvestmentScenarios, include_raw=True)

    # Step 2: compute composite scores (rule-based)
    scored = []
    for sc in scorecards:
        composite, ma = _composite(sc, cfg)
        rec            = _recommendation(sc, composite, cfg)
        scored.append({
            "scorecard":       sc,
            "composite_score": composite,
            "market_alignment": ma,
            "recommendation":  rec,
            "synthesis":       {},
            "scenarios":       {},
        })

    print(f"  L10: {len(scored)} targets | provider={provider} | max_workers={max_workers}")
    for item in sorted(scored, key=lambda x: -x["composite_score"]):
        sc = item["scorecard"]
        print(f"    {sc['target_entity']:22s}  composite={item['composite_score']}  ma={item['market_alignment']}  rec={item['recommendation']}")

    # Phase 1: synthesis for all targets in parallel
    synth_ok = 0
    synth_fail = 0
    idx_by_tid = {item["scorecard"]["target_id"]: item for item in scored}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures: dict = {}
        for item in scored:
            sc  = item["scorecard"]
            tid = sc["target_id"]
            futures[ex.submit(
                run_synthesis,
                sc, item["composite_score"],
                synthesis_chain, _call_id(), log_path, lock, model_name,
            )] = tid

        for fut in as_completed(futures):
            tid = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                result = {"parsed_ok": False, "error": str(e)}
            idx_by_tid[tid]["synthesis"] = result
            if result.get("parsed_ok"):
                synth_ok += 1
                print(f"    ✓ {tid} synthesis")
            else:
                synth_fail += 1
                print(f"    ✗ {tid} synthesis: {result.get('error', result.get('parse_error', '?'))}")

    # Phase 2: scenarios for all targets in parallel
    scen_ok = 0
    scen_fail = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures2: dict = {}
        for item in scored:
            sc  = item["scorecard"]
            tid = sc["target_id"]
            res = sc.get("resolution", {})
            if res.get("type") == "unresolved" or not res.get("tickers"):
                print(f"    ⊘ {sc['target_entity']} scenarios skipped (no tickers)")
                continue
            futures2[ex.submit(
                run_scenarios,
                sc, item["composite_score"], item["synthesis"],
                scenarios_chain, _call_id(), log_path, lock, model_name,
            )] = tid

        for fut in as_completed(futures2):
            tid = futures2[fut]
            try:
                result = fut.result()
            except Exception as e:
                result = {"parsed_ok": False, "error": str(e)}
            idx_by_tid[tid]["scenarios"] = result
            if result.get("parsed_ok"):
                scen_ok += 1
                print(f"    ✓ {tid} scenarios")
            else:
                scen_fail += 1
                print(f"    ✗ {tid} scenarios: {result.get('error', result.get('parse_error', '?'))}")

    # Rank by composite score
    ranked = sorted(scored, key=lambda x: -x["composite_score"])

    # Grab macro context from first scorecard (global for the run)
    macro = scorecards[0].get("macro_context", {})
    fii_threshold = cfg.get("fii_adj_threshold", 500)

    # Write final_report.md
    report_lines = [_build_market_header(macro, fii_threshold, date)]
    report_lines.append(f"\n_Generated: {datetime.now(IST).strftime('%Y-%m-%dT%H:%M:%S%z')}_\n")
    report_lines.append("\n---\n\n## Summary (ranked by composite score)\n")
    report_lines.append(_build_summary_table(ranked))
    for i, item in enumerate(ranked, 1):
        report_lines.append(_build_target_section(i, item))

    report_path = out_dir / "final_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    # Write watchlist_actions.json
    actions = []
    for item in ranked:
        sc  = item["scorecard"]
        syn = item["synthesis"]
        scn = item["scenarios"]
        res = sc.get("resolution", {})
        actions.append({
            "action":            "add",
            "target_entity":     sc["target_entity"],
            "resolution_type":   res.get("type", ""),
            "tickers":           res.get("tickers", []),
            "composite_score":   item["composite_score"],
            "market_alignment":  item["market_alignment"],
            "recommendation":    item["recommendation"],
            "entry_price_range": syn.get("entry_price_range", ""),
            "stop_loss_guide":   syn.get("stop_loss_guide", ""),
            "position_sizing_note": syn.get("position_sizing_note", ""),
            "conviction":        sc.get("thesis_validation", {}).get("conviction_level", ""),
            "time_horizon":      sc.get("time_horizon", ""),
            "exit_triggers":     syn.get("exit_triggers", []),
            "catalysts":         syn.get("catalysts", []),
            "bull_price_target": scn.get("bull_price_target"),
            "bull_return_pct":   scn.get("bull_return_pct"),
            "probability_bull":  scn.get("probability_bull"),
            "base_price_target": scn.get("base_price_target"),
            "base_return_pct":   scn.get("base_return_pct"),
            "probability_base":  scn.get("probability_base"),
            "bear_price_target": scn.get("bear_price_target"),
            "bear_return_pct":   scn.get("bear_return_pct"),
            "probability_bear":  scn.get("probability_bear"),
        })

    watchlist_path = out_dir / "watchlist_actions.json"
    watchlist_path.write_text(json.dumps({
        "run_date": date,
        "run_id":   manifest["run_id"],
        "actions":  actions,
    }, indent=2, ensure_ascii=False))

    # Memory write-back — facts only, no LLM prose
    mem_threshold = cfg.get("memory_threshold", 55)
    mem_count = 0
    with _DB_MEMORY.open("a", encoding="utf-8") as mf:
        for item in ranked:
            if item["composite_score"] >= mem_threshold:
                entry = _build_memory_entry(item, date, manifest["run_id"])
                mf.write(json.dumps(entry, ensure_ascii=False) + "\n")
                mem_count += 1

    elapsed = round(time.time() - t_start, 1)
    total_calls = len(scored) * 2
    all_ok   = synth_ok + scen_ok
    all_fail = synth_fail + scen_fail

    summary = {
        "run_date":          date,
        "total_targets":     len(scored),
        "llm_calls_total":   total_calls,
        "calls_ok":          all_ok,
        "calls_failed":      all_fail,
        "synthesis_ok":      synth_ok,
        "synthesis_fail":    synth_fail,
        "scenarios_ok":      scen_ok,
        "scenarios_fail":    scen_fail,
        "memory_entries":    mem_count,
        "elapsed_seconds":   elapsed,
        "scores": {
            item["scorecard"]["target_entity"]: {
                "composite": item["composite_score"],
                "market_alignment": item["market_alignment"],
                "recommendation": item["recommendation"],
            }
            for item in ranked
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"  L10 done: {len(scored)} targets | {all_ok}/{total_calls} ok | "
          f"{mem_count} memory entries | {elapsed}s")
    print(f"  Report: {report_path}")
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
