"""
L9 Specialist Analysis Agents — four LLM agents assess each deep-dive target.

Reads:
    output/{date}/run_manifest.json              → layer_9 config
    output/{date}/L8/evidence_packets.json       → self-contained evidence packets

Writes:
    output/{date}/L9/scorecards.json             → one scorecard per target (consumed by L10)
    output/{date}/L9/summary.json                → target counts, LLM stats, elapsed time
    output/{date}/L9/llm_calls.jsonl             → full prompt+response per LLM call

LLM: yes — 4 calls per target (fundamental, valuation, risk, thesis_validation)
     Provider + model from manifest layer_9 config.
     Phase 1: fundamental + valuation + risk run in parallel via ThreadPoolExecutor.
     Phase 2: thesis_validation runs after phase 1 completes (receives other 3 as context).

Module execution order:
    1. Load manifest → layer_9 config; load L8/evidence_packets.json
    2. Build LLM + 4 agent chains (one Pydantic schema per agent)
    3. Phase 1: submit fundamental+valuation+risk for all targets → ThreadPoolExecutor
    4. Phase 2: submit thesis_validation for all targets (with phase-1 results as context)
    5. Assemble scorecards; write scorecards.json + summary.json

Usage:
    python -m src.pipeline.L9_specialist.runner              # today
    python -m src.pipeline.L9_specialist.runner --date 2026-05-17
"""

import argparse
import itertools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, load_manifest, output_dir, today
from src.llm.client import make_llm
from src.pipeline.L9_specialist.agents import (
    FUNDAMENTAL_PROMPT,
    VALUATION_PROMPT,
    RISK_PROMPT,
    THESIS_PROMPT,
    FundamentalAssessment,
    ValuationAssessment,
    RiskAssessment,
    ThesisValidation,
    run_fundamental,
    run_valuation,
    run_risk,
    run_thesis_validation,
)


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _apply_risk_floor(risk: dict, market_data: dict) -> dict:
    """
    Post-process risk score: floor it upward when critical data is missing.
    LLM advisory instructions for data gaps aren't reliably enforced, so we
    apply a deterministic minimum here after the LLM returns its score.
    """
    missing_ownership = all(
        td.get("ownership", {}).get("promoter_pct") is None
        for td in market_data.values()
    ) if market_data else True

    missing_roe = all(
        td.get("fundamentals", {}).get("roe_pct") is None
        for td in market_data.values()
    ) if market_data else True

    floor = risk.get("score", 50)
    if missing_ownership and missing_roe:
        floor = max(floor, 70)
    elif missing_ownership or missing_roe:
        floor = max(floor, 60)

    if floor != risk.get("score"):
        risk = dict(risk)
        risk["score"] = floor
        parts = []
        if missing_ownership:
            parts.append("ownership data absent")
        if missing_roe:
            parts.append("ROE absent")
        note = f"Risk floor applied ({', '.join(parts)}) → score raised to {floor}"
        risk["key_findings"] = list(risk.get("key_findings", [])) + [note]
    return risk


def run(run_date: str | None = None) -> Path:
    t_start = time.time()
    date    = run_date or today()

    manifest = load_manifest(date)
    cfg      = manifest["layer_9"]

    packets_path = output_dir(date) / "L8" / "evidence_packets.json"
    if not packets_path.exists():
        raise FileNotFoundError(f"L8 output not found: {packets_path}")
    packets = json.loads(packets_path.read_text())["packets"]
    if not packets:
        raise ValueError("L8 evidence_packets.json contains no packets")

    provider    = cfg.get("provider", "openai")
    model       = cfg.get("model") or None
    max_workers = int(cfg.get("max_workers", 4))

    llm        = make_llm(provider=provider, model=model)
    model_name = getattr(llm, "model_name", None) or model or provider

    out_dir  = output_dir(date) / "L9"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "llm_calls.jsonl"
    lock     = threading.Lock()
    counter  = itertools.count(1)

    def _call_id() -> str:
        return f"L9_{date.replace('-', '')}_{'%04d' % next(counter)}"

    fundamental_chain = FUNDAMENTAL_PROMPT | llm.with_structured_output(FundamentalAssessment, include_raw=True)
    valuation_chain   = VALUATION_PROMPT   | llm.with_structured_output(ValuationAssessment,   include_raw=True)
    risk_chain        = RISK_PROMPT        | llm.with_structured_output(RiskAssessment,         include_raw=True)
    thesis_chain      = THESIS_PROMPT      | llm.with_structured_output(ThesisValidation,       include_raw=True)

    print(f"  L9: {len(packets)} targets | provider={provider} | max_workers={max_workers}")

    # Phase 1: fundamental + valuation + risk for all targets in parallel
    phase1: dict[str, dict] = {p["target_id"]: {} for p in packets}
    phase1_ok = 0
    phase1_fail = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures: dict = {}
        for pkt in packets:
            tid = pkt["target_id"]
            futures[ex.submit(run_fundamental, pkt, fundamental_chain, _call_id(), log_path, lock, model_name)] = (tid, "fundamental")
            futures[ex.submit(run_valuation,   pkt, valuation_chain,   _call_id(), log_path, lock, model_name)] = (tid, "valuation")
            futures[ex.submit(run_risk,        pkt, risk_chain,        _call_id(), log_path, lock, model_name)] = (tid, "risk")

        for fut in as_completed(futures):
            tid, agent = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                result = {"parsed_ok": False, "error": str(e)}
            phase1[tid][agent] = result
            if result.get("parsed_ok"):
                phase1_ok += 1
                print(f"    ✓ {tid} {agent}")
            else:
                phase1_fail += 1
                print(f"    ✗ {tid} {agent}: {result.get('error', result.get('parse_error', '?'))}")

    # Phase 2: thesis_validation (needs phase1)
    thesis_ok = 0
    thesis_fail = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures2: dict = {}
        for pkt in packets:
            tid = pkt["target_id"]
            futures2[ex.submit(
                run_thesis_validation,
                pkt, phase1[tid], thesis_chain, _call_id(), log_path, lock, model_name,
            )] = tid

        for fut in as_completed(futures2):
            tid = futures2[fut]
            try:
                result = fut.result()
            except Exception as e:
                result = {"parsed_ok": False, "error": str(e)}
            phase1[tid]["thesis_validation"] = result
            if result.get("parsed_ok"):
                thesis_ok += 1
                print(f"    ✓ {tid} thesis_validation")
            else:
                thesis_fail += 1
                print(f"    ✗ {tid} thesis_validation: {result.get('error', result.get('parse_error', '?'))}")

    # Assemble scorecards
    scorecards = []
    for pkt in packets:
        tid = pkt["target_id"]
        r   = phase1[tid]

        price_data: dict = {}
        for ticker, tdata in pkt.get("market_data", {}).items():
            p  = tdata.get("price", {})
            ac = tdata.get("analyst_consensus", {})
            price_data[ticker] = {
                "current":        p.get("current"),
                "analyst_target": ac.get("target_price_mean"),
                "upside_pct":     ac.get("upside_pct"),
                "analyst_count":  ac.get("analyst_count"),
            }

        risk_result = _apply_risk_floor(r.get("risk", {}), pkt.get("market_data", {}))

        scorecards.append({
            "target_id":         tid,
            "target_entity":     pkt["target_entity"],
            "bucket":            pkt["bucket"],
            "score":             pkt.get("score"),
            "time_horizon":      pkt.get("time_horizon"),
            "strength":          pkt.get("strength"),
            "thesis":            pkt.get("thesis", {}),
            "resolution":        pkt.get("resolution", {}),
            "macro_context":     pkt.get("macro_context", {}),
            "price_data":        price_data,
            "fundamental":       r.get("fundamental", {}),
            "valuation":         r.get("valuation", {}),
            "risk":              risk_result,
            "thesis_validation": r.get("thesis_validation", {}),
        })

    out = {
        "run_date":      date,
        "run_id":        manifest["run_id"],
        "total_targets": len(scorecards),
        "scorecards":    scorecards,
    }
    out_path = out_dir / "scorecards.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    elapsed = round(time.time() - t_start, 1)
    total_calls = len(packets) * 4
    all_ok = phase1_ok + thesis_ok
    all_fail = phase1_fail + thesis_fail

    summary = {
        "run_date":         date,
        "total_targets":    len(scorecards),
        "llm_calls_total":  total_calls,
        "calls_ok":         all_ok,
        "calls_failed":     all_fail,
        "phase1_ok":        phase1_ok,
        "phase1_fail":      phase1_fail,
        "thesis_ok":        thesis_ok,
        "thesis_fail":      thesis_fail,
        "elapsed_seconds":  elapsed,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"  L9 done: {len(scorecards)} scorecards | {all_ok}/{total_calls} ok | {elapsed}s")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
