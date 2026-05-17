"""
Two LLM agents for L10.

Agent 1 — synthesis: qualitative investment narrative + recommendation + entry/stop/catalysts.
Agent 2 — scenarios: bull/base/bear cases with specific ₹ price targets from current prices.

Both follow the L9 pattern: chain.invoke() → with_structured_output(Schema, include_raw=True)
→ _log_call() → return dict.

Phase 1 runs synthesis for all targets in parallel.
Phase 2 runs scenarios for all targets in parallel — receives synthesis result as context.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.config.settings import IST


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class InvestmentNarrative(BaseModel):
    investment_narrative: str    # 3-4 paragraphs: evidence, conclusion, risk, timing
    recommendation: Literal["strong_buy", "buy", "avoid"]
    entry_price_range: str       # specific ₹ range, e.g. "₹1,110–1,130 on dips"
    stop_loss_guide: str         # specific ₹ level, e.g. "₹950 (key support, -15%)"
    exit_triggers: list[str]     # 3-5 observable events that would invalidate thesis
    position_sizing_note: str    # "core position (3-5%)" / "half-size (1-2%)" / etc.
    catalysts: list[str]         # 3-5 near-term catalysts that could accelerate thesis


class InvestmentScenarios(BaseModel):
    bull_case: str
    bull_price_target: float     # absolute ₹ price, not %
    bull_return_pct: float       # % return from current price
    base_case: str
    base_price_target: float
    base_return_pct: float
    bear_case: str
    bear_price_target: float
    bear_return_pct: float       # typically negative
    probability_bull: int        # MUST sum to 100 with base + bear
    probability_base: int
    probability_bear: int


# ---------------------------------------------------------------------------
# Score anchor
# ---------------------------------------------------------------------------

_RECOMMENDATION_ANCHOR = (
    "Recommendation must match composite_score exactly:\n"
    "  strong_buy : composite_score ≥ 70\n"
    "  buy        : composite_score 55–69\n"
    "  avoid      : composite_score < 55\n"
    "Do NOT upgrade or downgrade from what the score mandates.\n"
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYNTHESIS_PROMPT = ChatPromptTemplate.from_template(
    "You are a senior investment analyst writing a final synthesis for a researched target.\n"
    "Synthesize all specialist assessments into an actionable investment view.\n\n"
    "Target: {target_entity}\n"
    "Time Horizon: {time_horizon}\n"
    "Composite Score: {composite_score}/100  (F={f_score} | V={v_score} | R={r_score} | T={t_score})\n\n"
    "INVESTMENT THESIS:\n{hypothesis}\n\n"
    "SPECIALIST ASSESSMENTS:\n"
    "Fundamental ({f_score}/100):\n{fundamental_findings}\n"
    "Fundamental Concerns: {fundamental_concerns}\n\n"
    "Valuation ({v_score}/100):\n{valuation_findings}\n"
    "Valuation Concerns: {valuation_concerns}\n\n"
    "Risk ({r_score}/100):\n{risk_flags}\n\n"
    "Thesis Validation ({t_score}/100):\n{thesis_findings}\n"
    "Thesis Q&A: {thesis_questions}\n\n"
    "INVALIDATION CONDITIONS (from thesis):\n{invalidation_check}\n\n"
    "PRICE DATA:\n{price_summary}\n\n"
    "INSTRUCTIONS:\n"
    "{recommendation_anchor}\n"
    "- investment_narrative: write 3-4 paragraphs covering: (1) what the evidence shows, "
    "(2) your key investment conclusion, (3) primary risk, (4) why act now or wait.\n"
    "- entry_price_range: specific ₹ range based on current prices (e.g. '₹1,110–1,130 on dips'). "
    "For sector baskets, anchor to the most liquid representative ticker.\n"
    "- stop_loss_guide: specific ₹ level with brief rationale (e.g. '₹950 (key support, -15% from entry)').\n"
    "- exit_triggers: 3-5 concrete observable events that would invalidate the thesis. "
    "Derive from the invalidation conditions — make each one actionable.\n"
    "- position_sizing_note: one sentence. Scale with conviction: "
    "strong_buy → core position (3-5%), buy → half-size (1-2%), avoid → no position.\n"
    "- catalysts: 3-5 near-term observable events that could accelerate the thesis.\n"
)

SCENARIOS_PROMPT = ChatPromptTemplate.from_template(
    "You are a research analyst computing specific price scenarios for an investment target.\n\n"
    "Target: {target_entity}\n"
    "Time Horizon: {time_horizon}\n"
    "Composite Score: {composite_score}/100\n\n"
    "INVESTMENT THESIS:\n{hypothesis}\n\n"
    "CURRENT PRICES AND ANALYST TARGETS:\n{price_data_block}\n\n"
    "INVESTMENT NARRATIVE (from synthesis step):\n{investment_narrative}\n\n"
    "INSTRUCTIONS:\n"
    "Produce three scenarios with specific ₹ price targets and % returns.\n\n"
    "base_case (probability ~50-60%): most likely outcome. "
    "Target should align with analyst consensus mean. 1-2 sentence description.\n\n"
    "bull_case (probability ~20-30%): optimistic. "
    "Target = analyst mean + 15-20% premium if catalysts deliver. 1-2 sentence description.\n\n"
    "bear_case (probability ~15-25%): downside. "
    "Target = current price impacted by the worst invalidating condition. "
    "1-2 sentence description of what went wrong.\n\n"
    "For price targets: use the PRIMARY ticker's current price as anchor. "
    "If it is a sector basket, pick the most liquid/representative ticker from the price data above.\n\n"
    "Compute return_pct = (price_target - current_price) / current_price × 100.\n"
    "Bear return_pct is typically negative.\n\n"
    "probability_bull + probability_base + probability_bear MUST sum to exactly 100.\n"
)


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _fmt_price_data(price_data: dict) -> str:
    lines = []
    for ticker, d in price_data.items():
        current = d.get("current")
        target  = d.get("analyst_target")
        upside  = d.get("upside_pct")
        count   = d.get("analyst_count")
        if current is not None:
            lines.append(
                f"  {ticker}: current=₹{current}  analyst_target=₹{target}  "
                f"upside={upside}%  analysts={count}"
            )
    return "\n".join(lines) or "  (no price data)"


def _fmt_bullet_list(items: list) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {item}" for item in items)


def _fmt_assessment_summary(assessment: dict, fields: list[str]) -> str:
    lines = []
    for f in fields:
        v = assessment.get(f)
        if v is not None:
            lines.append(f"  {f}: {v}")
    return "\n".join(lines) or "  (no data)"


# ---------------------------------------------------------------------------
# Shared log writer
# ---------------------------------------------------------------------------

def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _log_call(log_path: Path, lock: threading.Lock, entry: dict) -> None:
    with lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Agent functions
# ---------------------------------------------------------------------------

def run_synthesis(
    scorecard: dict,
    composite_score: int,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    target_entity = scorecard["target_entity"]
    thesis        = scorecard.get("thesis", {})
    price_data    = scorecard.get("price_data", {})
    f_sc          = scorecard.get("fundamental", {})
    v_sc          = scorecard.get("valuation", {})
    r_sc          = scorecard.get("risk", {})
    t_sc          = scorecard.get("thesis_validation", {})

    f_score = f_sc.get("score", 50)
    v_score = v_sc.get("score", 50)
    r_score = r_sc.get("score", 50)
    t_score = t_sc.get("score", 50)

    prompt_vars = {
        "target_entity":        target_entity,
        "time_horizon":         scorecard.get("time_horizon", ""),
        "composite_score":      composite_score,
        "f_score":              f_score,
        "v_score":              v_score,
        "r_score":              r_score,
        "t_score":              t_score,
        "hypothesis":           thesis.get("hypothesis", ""),
        "fundamental_findings": _fmt_bullet_list(f_sc.get("key_findings", [])),
        "fundamental_concerns": _fmt_bullet_list(f_sc.get("concerns", [])),
        "valuation_findings":   _fmt_bullet_list(v_sc.get("key_findings", [])),
        "valuation_concerns":   _fmt_bullet_list(v_sc.get("concerns", [])),
        "risk_flags":           _fmt_bullet_list(
                                    r_sc.get("red_flags", []) + r_sc.get("key_findings", [])
                                ),
        "thesis_findings":      _fmt_bullet_list(t_sc.get("key_findings", [])),
        "thesis_questions":     _fmt_bullet_list(t_sc.get("question_answers", [])),
        "invalidation_check":   _fmt_bullet_list(t_sc.get("invalidation_check", [])),
        "price_summary":        _fmt_price_data(price_data),
        "recommendation_anchor": _RECOMMENDATION_ANCHOR,
    }

    t0 = time.time()
    try:
        raw_result   = chain.invoke(prompt_vars)
        parsed       = raw_result.get("parsed")
        raw_msg      = raw_result.get("raw")
        parse_err    = raw_result.get("parsing_error")
        usage        = getattr(raw_msg, "usage_metadata", {}) or {}
        tokens_in    = usage.get("input_tokens", 0)
        tokens_out   = usage.get("output_tokens", 0)
        parsed_ok    = parsed is not None and parse_err is None
        extraction   = parsed.model_dump() if parsed_ok else {}
        response_str = parsed.model_dump_json() if parsed_ok else str(parse_err)
    except Exception as e:
        tokens_in = tokens_out = 0
        parsed_ok    = False
        extraction   = {}
        response_str = str(e)

    latency_ms = round((time.time() - t0) * 1000)
    _log_call(log_path, lock, {
        "call_id":    call_id,
        "timestamp":  _now_ist(),
        "layer":      "L10",
        "trigger":    f"target:{target_entity}:synthesis",
        "model":      model_name,
        "prompt":     SYNTHESIS_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}


def run_scenarios(
    scorecard: dict,
    composite_score: int,
    synthesis_result: dict,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    target_entity = scorecard["target_entity"]
    thesis        = scorecard.get("thesis", {})
    price_data    = scorecard.get("price_data", {})

    prompt_vars = {
        "target_entity":        target_entity,
        "time_horizon":         scorecard.get("time_horizon", ""),
        "composite_score":      composite_score,
        "hypothesis":           thesis.get("hypothesis", ""),
        "price_data_block":     _fmt_price_data(price_data),
        "investment_narrative": synthesis_result.get("investment_narrative", ""),
    }

    t0 = time.time()
    try:
        raw_result   = chain.invoke(prompt_vars)
        parsed       = raw_result.get("parsed")
        raw_msg      = raw_result.get("raw")
        parse_err    = raw_result.get("parsing_error")
        usage        = getattr(raw_msg, "usage_metadata", {}) or {}
        tokens_in    = usage.get("input_tokens", 0)
        tokens_out   = usage.get("output_tokens", 0)
        parsed_ok    = parsed is not None and parse_err is None
        extraction   = parsed.model_dump() if parsed_ok else {}
        response_str = parsed.model_dump_json() if parsed_ok else str(parse_err)
    except Exception as e:
        tokens_in = tokens_out = 0
        parsed_ok    = False
        extraction   = {}
        response_str = str(e)

    latency_ms = round((time.time() - t0) * 1000)
    _log_call(log_path, lock, {
        "call_id":    call_id,
        "timestamp":  _now_ist(),
        "layer":      "L10",
        "trigger":    f"target:{target_entity}:scenarios",
        "model":      model_name,
        "prompt":     SCENARIOS_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}
