"""
Four specialist LLM agents for L9.

Each agent function:
  - Builds prompt vars from the evidence packet
  - Invokes its LangChain chain (passed in from runner)
  - Logs the call to llm_calls.jsonl
  - Returns a flat dict {parsed_ok, ...assessment fields}

Agent execution order:
  Phase 1 (parallel): fundamental, valuation, risk
  Phase 2 (after phase 1): thesis_validation — receives phase-1 dicts as context

Fixes applied vs v1:
  1. Score anchoring: calibration scale added to all 4 prompts so scores spread across
     the full 0-100 range rather than clustering 52-75.
  2. Bank-aware fundamentals: prompt and format helper detect financial institutions
     and switch from OPM framing to NIM/GNPA/ROE framing.
  3. Structured invalidation check: ThesisValidation gains invalidation_check field;
     thesis prompt forces per-condition status (not_triggered/watch/imminent).
  4. Time-horizon-aware valuation: time_horizon flows to valuation agent; prompt
     interprets PE/upside differently for short vs medium vs long-term theses.
  5. Corporate events in risk: recent_filings and corporate_actions added to risk
     context so management changes, credit ratings, results announcements are visible.
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

class FundamentalAssessment(BaseModel):
    score: int                    # 0-100, higher = better quality business
    verdict: Literal["strong", "adequate", "weak", "insufficient_data"]
    revenue_quality: str          # revenue trend and consistency
    margin_trend: str             # margin/NIM/spread direction and sustainability
    moat_indicators: list[str]    # competitive advantages identified
    management_signals: str       # management quality signals from news/filings
    key_findings: list[str]       # 3-4 most important fundamental observations
    concerns: list[str]           # specific fundamental weaknesses
    data_gaps_impact: str         # how missing data affects confidence


class ValuationAssessment(BaseModel):
    score: int                           # 0-100, higher = more undervalued
    verdict: Literal["undervalued", "fairly_valued", "overvalued", "insufficient_data"]
    pe_assessment: str                   # PE vs sector/history given time horizon
    upside_to_fair_value_pct: float | None  # % to analyst target price
    margin_of_safety: str                # buffer to intrinsic value
    analyst_consensus_alignment: str     # buy/hold/sell count interpretation
    time_horizon_fit: str                # does current valuation suit the time horizon?
    key_findings: list[str]
    concerns: list[str]


class RiskAssessment(BaseModel):
    score: int                    # 0-100, higher = MORE risk (L10 uses 100-risk)
    verdict: Literal["low", "moderate", "high", "very_high"]
    red_flags: list[str]          # specific warning signals from data, news, corporate events
    data_gap_risks: list[str]     # risks from missing evidence
    macro_risk: str               # regime + FII/DII flow risk
    invalidation_proximity: str   # how close are the invalidating conditions?
    key_findings: list[str]


class ThesisValidation(BaseModel):
    score: int                    # 0-100, higher = stronger evidence support
    verdict: Literal["strongly_supported", "supported", "mixed", "contradicted", "insufficient_data"]
    evidence_alignment: str       # how well news evidence supports hypothesis
    question_answers: list[str]   # one answer per deep_dive_question
    invalidation_check: list[str] # per-condition: "[condition]. Status: not_triggered|watch|imminent. Evidence: [one sentence]."
    bull_case: str                # strongest supporting evidence
    bear_case: str                # strongest contradicting evidence
    conviction_level: Literal["high", "medium", "low"]
    key_findings: list[str]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_FUNDAMENTAL_SCORE_ANCHOR = (
    "Score calibration:\n"
    "  90+  = elite franchise: 20%+ ROE, strong durable moat, exceptional management "
    "(e.g., Asian Paints, HDFC Bank pre-2020 quality)\n"
    "  70-89 = solid quality: defensible position, reasonable moat, good management\n"
    "  50-69 = adequate: some moat, notable data gaps, or mixed execution\n"
    "  30-49 = weak: declining margins, competitive pressure, management concerns\n"
    "  below 30 = poor: deteriorating fundamentals, no visible moat, high execution risk\n"
    "Be willing to score at extremes when data warrants it. "
    "Do not cluster around 55-70 out of caution.\n"
)

_VALUATION_SCORE_ANCHOR = (
    "Score calibration:\n"
    "  90+  = extreme undervaluation: 40%+ discount to fair value with strong earnings growth\n"
    "  70-89 = meaningfully undervalued: 15-35% discount, good risk/reward\n"
    "  50-69 = fairly valued: 0-15% upside, neutral risk/reward\n"
    "  30-49 = mildly overvalued: priced for perfection, thin margin of safety\n"
    "  below 30 = significantly overvalued: premium not justified by fundamentals\n"
    "Be willing to score at extremes. A stock at 35% discount to a credible target "
    "should score 75-85, not 60.\n"
)

_RISK_SCORE_ANCHOR = (
    "Score calibration (higher = MORE risk; L10 uses 100-risk in its formula):\n"
    "  80+  = very high: multiple active red flags, imminent invalidating conditions, "
    "promoter or governance concerns\n"
    "  60-79 = high: clear headwinds, some red flags, material data gaps\n"
    "  40-59 = moderate: manageable concerns, normal market risk, minor gaps\n"
    "  20-39 = low: well-covered thesis, no material red flags, strong data quality\n"
    "  below 20 = minimal: exceptionally well-supported with no visible threats\n"
    "Be willing to score at extremes. A target with 5+ red flags and null ownership "
    "data should score 75+, not 65.\n"
)

_THESIS_SCORE_ANCHOR = (
    "Score calibration:\n"
    "  90+  = strongly supported: multiple primary sources explicitly confirm thesis, "
    "no material contradictions\n"
    "  70-89 = well-supported: clear evidence alignment, minor gaps\n"
    "  50-69 = mixed: evidence partially supports, some contradictions or unanswered questions\n"
    "  30-49 = weakly supported: more contradicting evidence than supporting\n"
    "  below 30 = contradicted: primary sources directly contradict the thesis\n"
    "Be willing to score at extremes. Do not default to 60-65 when evidence is clearly "
    "strong or clearly weak.\n"
)

FUNDAMENTAL_PROMPT = ChatPromptTemplate.from_template(
    "You are a fundamental equity analyst assessing business quality for Indian markets.\n\n"
    "Target: {target_entity} (Bucket: {bucket}, Time horizon: {time_horizon})\n"
    "Investment thesis: {hypothesis}\n\n"
    "Market data per ticker:\n{market_data_block}\n\n"
    "Key facts from news:\n{news_facts}\n\n"
    "Key events from news:\n{news_events}\n\n"
    "Past context:\n{past_context}\n\n"
    "Data gaps:\n{data_gaps}\n\n"
    "Instructions:\n"
    "- score: 0-100 (higher = better quality business)\n"
    + _FUNDAMENTAL_SCORE_ANCHOR +
    "- verdict: strong (score ≥ 80) / adequate (50-79) / weak (30-49) / "
    "insufficient_data (cannot assess due to gaps)\n"
    "- revenue_quality: assess revenue trend, consistency, growth quality from quarterly data\n"
    "- margin_trend:\n"
    "    BANKS/FINANCIAL INSTITUTIONS (entity name contains 'Bank', 'Finance', 'NBFC', 'Financial'):\n"
    "      Assess NIM (net interest margin) trend and credit cost trajectory. "
    "The 'margin' field in quarterly data is a broad spread proxy for banks — "
    "interpret accordingly. GNPA/NNPA trend (even if null, note the gap), ROE, CASA advantage.\n"
    "    NON-FINANCIAL COMPANIES:\n"
    "      Assess OPM (operating profit margin) trend direction and sustainability.\n"
    "    COMMODITY/SECTOR TARGETS (multiple proxy tickers):\n"
    "      Assess GRM (gross refinery margin) for refiners, realization per unit for "
    "upstream, government pricing policy sensitivity.\n"
    "- moat_indicators: specific competitive advantages — pricing power, switching costs, "
    "network effects, regulatory moat, brand, cost leadership. Be specific, not generic.\n"
    "- management_signals: what news, filings, and corporate events reveal about "
    "management quality and capital allocation discipline\n"
    "- key_findings: 3-4 most important fundamental observations\n"
    "- concerns: specific fundamental weaknesses. Be direct — name the specific concern.\n"
    "- data_gaps_impact: how null fields affect your confidence and which analysis is blocked\n"
    "For commodity/sector targets with multiple tickers, assess the group collectively "
    "and identify which ticker(s) are the primary thesis carriers.\n"
)

VALUATION_PROMPT = ChatPromptTemplate.from_template(
    "You are a valuation analyst assessing whether Indian equities are attractively priced.\n\n"
    "Target: {target_entity} (Bucket: {bucket})\n"
    "Time horizon: {time_horizon}\n"
    "Investment thesis: {hypothesis}\n\n"
    "Price, valuation, and earnings data per ticker:\n{market_data_block}\n\n"
    "Data gaps:\n{data_gaps}\n\n"
    "Instructions:\n"
    "- score: 0-100 (higher = more undervalued / better value for this time horizon)\n"
    + _VALUATION_SCORE_ANCHOR +
    "- verdict: undervalued / fairly_valued / overvalued / insufficient_data\n"
    "- pe_assessment: interpret PE vs sector norms, history, and growth rate. "
    "Consider time horizon — short_term focuses on momentum and catalyst timing; "
    "medium_term uses forward PE and analyst target realization; "
    "long_term uses intrinsic value, PEG ratio, and compounding quality.\n"
    "- upside_to_fair_value_pct: compute from analyst target_price_mean vs current price; "
    "null if no analyst coverage\n"
    "- margin_of_safety: describe the buffer between current price and fair value. "
    "Be specific — '34% upside to consensus target of ₹1,670' not 'moderate buffer'.\n"
    "- analyst_consensus_alignment: interpret rec_mean (1=StrongBuy, 5=StrongSell) and target prices. "
    "State whether consensus supports entry at current price.\n"
    "- time_horizon_fit: does the current valuation specifically suit a {time_horizon} "
    "thesis? E.g., is there a near-term catalyst, or is this only compelling long-term?\n"
    "- key_findings: 3-4 most important valuation observations\n"
    "- concerns: overvaluation risks, missing data, or horizon mismatch\n"
    "For commodity/sector targets with multiple proxy tickers, assess each and "
    "highlight the best risk/reward entry point.\n"
)

RISK_PROMPT = ChatPromptTemplate.from_template(
    "You are a risk analyst identifying threats and red flags for an Indian equity position.\n\n"
    "Target: {target_entity} (Bucket: {bucket})\n"
    "Macro context: FII net {fii_net_cr}cr, DII net {dii_net_cr}cr, "
    "Nifty {nifty_change_pct}%, regime={regime}\n\n"
    "Thesis invalidating conditions:\n{invalidating_conditions}\n\n"
    "Technical and ownership data per ticker:\n{market_data_block}\n\n"
    "Recent corporate events (filings + actions):\n{corporate_events}\n\n"
    "Market signals from news:\n{news_signals}\n\n"
    "All evidence gaps:\n{data_gaps}\n\n"
    "Instructions:\n"
    "- score: 0-100 (higher = MORE risk)\n"
    + _RISK_SCORE_ANCHOR +
    "- verdict: low / moderate / high / very_high\n"
    "- red_flags: specific, concrete warning signals from data, technicals, ownership, "
    "news, and corporate events. Each flag should name the specific indicator and its value "
    "(e.g., 'RSI 28.9 — oversold but could indicate continued selling pressure' not 'RSI low').\n"
    "  IMPORTANT: check corporate events section for material filings in the last 30 days. "
    "Management changes, credit rating actions, board outcomes, QIPs, promoter stake sales "
    "are all red flag candidates.\n"
    "- data_gap_risks: concrete risks that arise from null fields — e.g., "
    "'NIM data missing — cannot assess if HDFC Bank's margin is compressing under rate pressure'\n"
    "- macro_risk: assess FII/DII flow direction + market regime as headwind/tailwind/neutral. "
    "Be specific about magnitude (e.g., FII net +1329cr is a modest tailwind, not transformative).\n"
    "- invalidation_proximity: for each invalidating condition, how likely/imminent is it "
    "given current evidence? Name the condition and give a one-line status.\n"
    "- key_findings: 3-4 most important risk observations\n"
)

THESIS_PROMPT = ChatPromptTemplate.from_template(
    "You are a thesis validation analyst determining whether evidence supports an "
    "investment hypothesis for an Indian equity target.\n\n"
    "Target: {target_entity}\n"
    "Hypothesis: {hypothesis}\n"
    "Beneficiaries: {beneficiaries}\n\n"
    "Deep dive questions to answer:\n{deep_dive_questions}\n\n"
    "Invalidating conditions:\n{invalidating_conditions}\n\n"
    "Supporting news evidence:\n{news_evidence}\n\n"
    "Fundamental assessment (score={fundamental_score}, verdict={fundamental_verdict}):\n"
    "{fundamental_summary}\n\n"
    "Valuation assessment (score={valuation_score}, verdict={valuation_verdict}):\n"
    "{valuation_summary}\n\n"
    "Risk assessment (score={risk_score}, verdict={risk_verdict}):\n"
    "{risk_summary}\n\n"
    "Instructions:\n"
    "- score: 0-100 (higher = evidence strongly supports thesis)\n"
    + _THESIS_SCORE_ANCHOR +
    "- verdict: strongly_supported / supported / mixed / contradicted / insufficient_data\n"
    "- evidence_alignment: does the news evidence directly corroborate the hypothesis? "
    "Be specific — cite the strongest article and what it confirms or contradicts.\n"
    "- question_answers: answer each deep_dive_question in order, one answer per question. "
    "Ground answers in the actual news evidence provided — cite sources.\n"
    "- invalidation_check: for EACH invalidating condition (in the same order as numbered "
    "above), write one string that: (1) copies the condition verbatim, (2) appends "
    "' | Status: ' followed by exactly ONE of: not_triggered / watch / imminent, "
    "(3) appends ' | Evidence: ' and one sentence citing what you found or did not find. "
    "Do NOT output all three status options — pick one. "
    "Example entry: 'A sustained crude price spike compresses OMC margins. | Status: watch. "
    "| Evidence: Brent near $108 per barrel documented in ET article dated May 16 2026; "
    "margins not yet confirmed compressed.' "
    "Definitions: not_triggered = no evidence; watch = early signs visible; "
    "imminent = evidence strongly suggests this materializes within 4 weeks.\n"
    "- bull_case: the single strongest piece of supporting evidence — cite source and specific fact\n"
    "- bear_case: the single strongest contradicting evidence or gap — be specific\n"
    "- conviction_level: high / medium / low — your integrated conviction across all four "
    "agent assessments. High = score 75+, fundamental+valuation both solid, no imminent "
    "invalidation. Low = score <50, or any invalidation watch/imminent.\n"
    "- key_findings: 3-4 most important thesis validation observations\n"
    "Use full article content where available (primary records) — "
    "prefer primary source text over summarized analysis.\n"
)


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _is_financial_target(target_entity: str) -> bool:
    """True if entity is a bank, NBFC, or financial institution."""
    lower = target_entity.lower()
    return any(kw in lower for kw in ("bank", "nbfc", "finance", "financial"))


def _fmt_fundamentals(market_data: dict, target_entity: str = "") -> str:
    is_financial = _is_financial_target(target_entity)
    lines = []
    for ticker, data in market_data.items():
        f  = data.get("fundamentals", {})
        ow = data.get("ownership", {})
        qt = data.get("quarterly_trend", [])
        lines.append(f"[{ticker}{'  (FINANCIAL — use NIM/ROE/GNPA framework)' if is_financial else ''}]")
        lines.append(
            f"  pe_ttm={f.get('pe_ttm')}  pb={f.get('pb')}  "
            f"roe={f.get('roe_pct')}%  roce={f.get('roce_pct')}%  "
            f"rev_growth={f.get('revenue_growth_ttm_pct')}%  "
            f"pat_growth={f.get('pat_growth_ttm_pct')}%  "
            f"div_yield={f.get('dividend_yield_pct')}%"
        )
        if is_financial:
            lines.append(
                f"  gross_npa={f.get('gross_npa_pct')}%  net_npa={f.get('net_npa_pct')}%  "
                f"nim={f.get('nim_pct')}%  promoter_pledge={ow.get('promoter_pledge_pct')}%"
            )
        if qt:
            label = "spread%" if is_financial else "opm%"
            for q in qt[-3:]:
                lines.append(
                    f"  {q.get('quarter','?')}: rev={q.get('revenue_cr')}cr  "
                    f"pat={q.get('pat_cr')}cr  {label}={q.get('opm_pct')}%"
                )
    return "\n".join(lines) or "  (no market data)"


def _fmt_valuation(market_data: dict) -> str:
    lines = []
    for ticker, data in market_data.items():
        p   = data.get("price", {})
        ac  = data.get("analyst_consensus", {})
        f   = data.get("fundamentals", {})
        qt  = data.get("quarterly_trend", [])
        lines.append(f"[{ticker}]")
        lines.append(
            f"  price={p.get('current')}  52w_high={p.get('52w_high')}  "
            f"pct_from_52w_high={p.get('pct_from_52w_high')}%  "
            f"return_30d={p.get('return_30d_pct')}%  rsi={p.get('rsi_14')}"
        )
        lines.append(
            f"  pe_ttm={f.get('pe_ttm')}  pb={f.get('pb')}  "
            f"forward_pe={ac.get('forward_pe')}  "
            f"target_price={ac.get('target_price_mean')}  "
            f"upside={ac.get('upside_pct')}%  "
            f"analysts={ac.get('analyst_count')}  "
            f"rec_mean={ac.get('recommendation_mean')} (1=StrongBuy 5=StrongSell)"
        )
        if qt:
            rev_trend = [f"{q.get('quarter','?')}: rev={q.get('revenue_cr')}cr pat={q.get('pat_cr')}cr"
                         for q in qt[-3:]]
            lines.append("  earnings_trend: " + " | ".join(rev_trend))
    return "\n".join(lines) or "  (no market data)"


def _fmt_risk_technicals(market_data: dict) -> str:
    lines = []
    for ticker, data in market_data.items():
        p  = data.get("price", {})
        ow = data.get("ownership", {})
        f  = data.get("fundamentals", {})
        lines.append(f"[{ticker}]")
        lines.append(
            f"  rsi={p.get('rsi_14')}  pct_from_52w_high={p.get('pct_from_52w_high')}%  "
            f"pct_above_200dma={p.get('pct_above_200dma')}%  "
            f"vol_ratio={p.get('volume_ratio_20d')}"
        )
        lines.append(
            f"  promoter_holding={ow.get('promoter_pct')}%  "
            f"promoter_pledge={ow.get('promoter_pledge_pct')}%  "
            f"fii_holding={ow.get('fii_pct')}%  "
            f"dii_holding={ow.get('dii_pct')}%  "
            f"fii_change_qoq={ow.get('fii_change_qoq_pct')}%"
        )
    return "\n".join(lines) or "  (no market data)"


def _fmt_corporate_events(market_data: dict) -> str:
    """Format recent_filings and corporate_actions for the risk agent."""
    _MATERIAL_TYPES = {
        "dividend", "change in director", "change in management",
        "outcome of board meeting", "credit rating", "qip", "ipo", "drhp",
        "buyback", "amalgamation", "merger", "financial results",
        "outcome of agm", "press release",
    }
    lines = []
    for ticker, data in market_data.items():
        filings  = data.get("recent_filings", [])
        corp_act = data.get("corporate_actions", [])
        ticker_lines = []

        for f in filings[:3]:
            ftype   = (f.get("type") or "").lower()
            date    = f.get("date", "")[:10]
            subject = (f.get("subject") or "")[:120]
            is_material = any(kw in ftype for kw in _MATERIAL_TYPES)
            flag = "  *** MATERIAL ***" if is_material else ""
            ticker_lines.append(f"  FILING [{date}] {f.get('type','?')}: {subject}{flag}")

        for ca in corp_act[:2]:
            ex_date = ca.get("ex_date", "")
            amount  = ca.get("amount", "")
            purpose = ca.get("purpose") or ca.get("type") or "dividend"
            if ex_date:
                ticker_lines.append(f"  ACTION ex={ex_date} amount={amount} ({purpose})")

        if ticker_lines:
            lines.append(f"[{ticker}]")
            lines.extend(ticker_lines)

    return "\n".join(lines) or "  (no recent corporate events)"


def _fmt_news_facts_events(supporting_news: list[dict]) -> tuple[str, str]:
    facts_lines:  list[str] = []
    events_lines: list[str] = []
    for rec in supporting_news:
        src = rec.get("source", "?")
        for fact in rec.get("key_facts", []):
            facts_lines.append(f"  [{src}] {fact.get('entity','')}: {fact.get('text','')} {fact.get('value','')}")
        for ev in rec.get("key_events", []):
            events_lines.append(f"  [{src} / {ev.get('direction','?')}] {ev.get('entity','')}: {ev.get('text','')}")
    return (
        "\n".join(facts_lines)  or "  (none)",
        "\n".join(events_lines) or "  (none)",
    )


def _fmt_news_signals(supporting_news: list[dict]) -> str:
    lines: list[str] = []
    for rec in supporting_news:
        src = rec.get("source", "?")
        for sig in rec.get("market_signals", []):
            lines.append(
                f"  [{src} / {sig.get('direction','?')} / conf={sig.get('confidence','?')}] "
                f"{sig.get('entity','')}: {sig.get('text','')}"
            )
    return "\n".join(lines) or "  (none)"


_DATA_GAP_TYPES = {"collection_failed", "collection_partial", "missing_field"}


def _fmt_gaps(gaps: list[dict], gap_type: str | set | None = None) -> str:
    if isinstance(gap_type, set):
        filtered = [g for g in gaps if g.get("type") in gap_type]
    else:
        filtered = [g for g in gaps if gap_type is None or g.get("type") == gap_type]
    if not filtered:
        return "  (none)"
    lines = []
    for g in filtered:
        if g.get("type") in _DATA_GAP_TYPES:
            field = g.get("field") or g.get("type", "?")
            lines.append(f"  [{g.get('ticker','?')}] {field} — blocks: {g.get('impact','?')}")
        else:
            lines.append(f"  Q: {g.get('question','?')[:80]} — {g.get('impact','?')}")
    return "\n".join(lines)


def _fmt_news_evidence(supporting_news: list[dict]) -> str:
    """For thesis_validation: full content for primary records, analysis for related records."""
    blocks: list[str] = []
    for rec in supporting_news:
        rtype    = rec.get("relevance_type", "entity_match")
        title    = rec.get("title", "")
        src      = rec.get("source", "?")
        content  = rec.get("content", "")
        analysis = rec.get("analysis", "")
        label    = "primary" if rtype == "hypothesis_source" else "related"
        header   = f"--- [{label} | {src}] {title}"
        if content:
            blocks.append(f"{header}\n{content[:3000]}")
        elif analysis:
            blocks.append(f"{header}\n{analysis}")
    return "\n\n".join(blocks) or "  (no news evidence)"


def _fmt_assessment_summary(assessment: dict, fields: list[str]) -> str:
    lines = []
    for f in fields:
        val = assessment.get(f)
        if val is not None:
            if isinstance(val, list):
                lines.append(f"  {f}: {'; '.join(str(v) for v in val[:3])}")
            else:
                lines.append(f"  {f}: {val}")
    return "\n".join(lines) or "  (not available)"


# ---------------------------------------------------------------------------
# Logging helper
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

def run_fundamental(
    packet: dict,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    market_data     = packet.get("market_data", {})
    thesis          = packet.get("thesis", {})
    supporting_news = packet.get("supporting_news", [])
    gaps            = packet.get("evidence_gaps", [])
    past_context    = packet.get("past_context", [])
    target_entity   = packet.get("target_entity", "")

    facts_str, events_str = _fmt_news_facts_events(supporting_news)

    past_lines = []
    for m in past_context[:5]:
        past_lines.append(f"  - {m.get('memory_type','?')} | {m.get('title','')}: {m.get('summary','')}")
    past_str = "\n".join(past_lines) or "  (none)"

    prompt_vars = {
        "target_entity":     target_entity,
        "bucket":            packet.get("bucket", ""),
        "time_horizon":      packet.get("time_horizon", ""),
        "hypothesis":        thesis.get("hypothesis", ""),
        "market_data_block": _fmt_fundamentals(market_data, target_entity),
        "news_facts":        facts_str,
        "news_events":       events_str,
        "past_context":      past_str,
        "data_gaps":         _fmt_gaps(gaps, _DATA_GAP_TYPES),
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
        "layer":      "L9",
        "trigger":    f"target:{target_entity}:fundamental",
        "model":      model_name,
        "prompt":     FUNDAMENTAL_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}


def run_valuation(
    packet: dict,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    market_data   = packet.get("market_data", {})
    thesis        = packet.get("thesis", {})
    gaps          = packet.get("evidence_gaps", [])
    target_entity = packet.get("target_entity", "")

    prompt_vars = {
        "target_entity":     target_entity,
        "bucket":            packet.get("bucket", ""),
        "time_horizon":      packet.get("time_horizon", ""),
        "hypothesis":        thesis.get("hypothesis", ""),
        "market_data_block": _fmt_valuation(market_data),
        "data_gaps":         _fmt_gaps(gaps, _DATA_GAP_TYPES),
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
        "layer":      "L9",
        "trigger":    f"target:{target_entity}:valuation",
        "model":      model_name,
        "prompt":     VALUATION_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}


def run_risk(
    packet: dict,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    market_data     = packet.get("market_data", {})
    thesis          = packet.get("thesis", {})
    gaps            = packet.get("evidence_gaps", [])
    macro           = packet.get("macro_context", {})
    supporting_news = packet.get("supporting_news", [])
    target_entity   = packet.get("target_entity", "")

    inv_cond = thesis.get("invalidating_conditions", [])
    inv_str  = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(inv_cond)) or "  (none)"

    prompt_vars = {
        "target_entity":          target_entity,
        "bucket":                 packet.get("bucket", ""),
        "fii_net_cr":             macro.get("fii_net_cr", "N/A"),
        "dii_net_cr":             macro.get("dii_net_cr", "N/A"),
        "nifty_change_pct":       macro.get("nifty_change_pct", "N/A"),
        "regime":                 macro.get("regime", "unknown"),
        "invalidating_conditions": inv_str,
        "market_data_block":      _fmt_risk_technicals(market_data),
        "corporate_events":       _fmt_corporate_events(market_data),
        "news_signals":           _fmt_news_signals(supporting_news),
        "data_gaps":              _fmt_gaps(gaps),
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
        "layer":      "L9",
        "trigger":    f"target:{target_entity}:risk",
        "model":      model_name,
        "prompt":     RISK_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}


def run_thesis_validation(
    packet: dict,
    phase1: dict,
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    thesis          = packet.get("thesis", {})
    supporting_news = packet.get("supporting_news", [])
    target_entity   = packet.get("target_entity", "")

    fundamental = phase1.get("fundamental", {})
    valuation   = phase1.get("valuation", {})
    risk        = phase1.get("risk", {})

    questions   = thesis.get("deep_dive_questions", [])
    q_str       = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions)) or "  (none)"

    inv_cond    = thesis.get("invalidating_conditions", [])
    inv_str     = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(inv_cond)) or "  (none)"

    bene_str    = ", ".join(thesis.get("beneficiaries", [])) or "(none)"

    prompt_vars = {
        "target_entity":        target_entity,
        "hypothesis":           thesis.get("hypothesis", ""),
        "beneficiaries":        bene_str,
        "deep_dive_questions":  q_str,
        "invalidating_conditions": inv_str,
        "news_evidence":        _fmt_news_evidence(supporting_news),
        "fundamental_score":    fundamental.get("score", "N/A"),
        "fundamental_verdict":  fundamental.get("verdict", "N/A"),
        "fundamental_summary":  _fmt_assessment_summary(
            fundamental, ["revenue_quality", "margin_trend", "key_findings", "concerns"]
        ),
        "valuation_score":      valuation.get("score", "N/A"),
        "valuation_verdict":    valuation.get("verdict", "N/A"),
        "valuation_summary":    _fmt_assessment_summary(
            valuation, ["pe_assessment", "upside_to_fair_value_pct", "time_horizon_fit",
                        "key_findings", "concerns"]
        ),
        "risk_score":           risk.get("score", "N/A"),
        "risk_verdict":         risk.get("verdict", "N/A"),
        "risk_summary":         _fmt_assessment_summary(
            risk, ["macro_risk", "invalidation_proximity", "red_flags", "key_findings"]
        ),
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
        "layer":      "L9",
        "trigger":    f"target:{target_entity}:thesis_validation",
        "model":      model_name,
        "prompt":     THESIS_PROMPT.format(**prompt_vars),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    })
    return {"parsed_ok": parsed_ok, **extraction}
