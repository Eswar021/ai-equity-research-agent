"""
L5 Hypothesis Generation — groups signals into investable themes and generates one hypothesis per group via LLM.

Reads:
    output/{date}/run_manifest.json          → layer_5 config
    output/{date}/L4/memory_context.json     → enriched records + recalled memory

Writes:
    output/{date}/L5/hypotheses.json         → one hypothesis per signal group (consumed by L6)
    output/{date}/L5/market_regime.json      → rule-based market regime (bull/bear/sideways/uncertain)
    output/{date}/L5/summary.json            → group counts, LLM stats, weight distribution
    output/{date}/L5/llm_calls.jsonl         → full prompt+response per LLM call

LLM: yes — one call per signal group, parallel via ThreadPoolExecutor
     Provider + model from manifest layer_5 config.

Module execution order:
    1. Load manifest → layer_5 config; build LLM chain
    2. Load L4/memory_context.json → records + memory[]
    3. BUILD GROUPS:
       a. Theme-centric: for each unique theme, collect ALL records containing that theme
       b. Entity-centric (orphans only): entities not covered by any theme group
    4. WEIGHT + FILTER + SORT groups → top max_hypotheses
    5. MARKET REGIME — scan market_snapshot records → write market_regime.json
    6. LLM CALLS in parallel → one HypothesisOutput per group
    7. Write hypotheses.json + summary.json + llm_calls.jsonl

Usage:
    python -m src.pipeline.L5_hypothesis.runner              # today
    python -m src.pipeline.L5_hypothesis.runner --date 2026-05-17
"""

import argparse
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.config.settings import IST, load_manifest, output_dir, today
from src.llm.client import make_llm


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class HypothesisOutput(BaseModel):
    hypothesis:              str
    beneficiaries:           list[str]
    time_horizon:            Literal["intraday", "short_term", "medium_term", "long_term"]
    strength:                Literal["strong", "medium", "weak"]
    deep_dive_questions:     list[str]
    invalidating_conditions: list[str]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT = ChatPromptTemplate.from_template(
    "You are an investment intelligence analyst. Based on the signal group below, "
    "generate one clear, investable hypothesis.\n\n"
    "Group name: {group_name}\n"
    "Group type: {group_type}\n"
    "Entities involved: {entities}\n\n"
    "Events (strongest signals):\n{events}\n\n"
    "Market signals:\n{signals}\n\n"
    "Supporting facts:\n{facts}\n\n"
    "Recalled past context:\n{memory_context}\n\n"
    "Instructions:\n"
    "- hypothesis: one actionable investment thesis (2-3 sentences)\n"
    "- beneficiaries: specific companies, indices, or sectors that benefit\n"
    "- time_horizon: intraday / short_term (days-weeks) / medium_term (1-3 months) / long_term (3m+)\n"
    "- strength: strong / medium / weak based on signal quality and breadth\n"
    "- deep_dive_questions: 3 specific questions to validate or sharpen this thesis\n"
    "- invalidating_conditions: 3 concrete events that would kill this thesis\n"
)


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------

def _build_groups(records: list[dict], memory: list[dict]) -> list[dict]:
    """Build theme-centric groups first, then entity-centric for uncovered entities."""

    # --- theme-centric groups ---
    theme_to_records: dict[str, list[dict]] = {}
    for rec in records:
        for theme in rec.get("themes", []):
            t = theme.strip()
            if t:
                theme_to_records.setdefault(t, []).append(rec)

    theme_groups: list[dict] = []
    theme_covered_entities: set[str] = set()

    for theme, recs in theme_to_records.items():
        entities, events, signals, facts, record_ids, sources = _union_group(recs)
        theme_covered_entities.update(e.lower() for e in entities)
        theme_groups.append({
            "group_type":  "theme_centric",
            "group_name":  theme,
            "entities":    sorted(entities),
            "events":      events,
            "market_signals": signals,
            "facts":       facts,
            "record_ids":  sorted(set(record_ids)),
            "sources":     sorted(sources),
        })

    # --- entity-centric groups (orphans only) ---
    entity_to_records: dict[str, list[dict]] = {}
    for rec in records:
        for ent in rec.get("entities", []):
            name = ent.get("name", "").strip()
            if name and name.lower() not in theme_covered_entities:
                entity_to_records.setdefault(name, []).append(rec)

    entity_groups: list[dict] = []
    for entity, recs in entity_to_records.items():
        entities, events, signals, facts, record_ids, sources = _union_group(recs)
        entity_groups.append({
            "group_type":  "entity_centric",
            "group_name":  entity,
            "entities":    sorted(entities),
            "events":      events,
            "market_signals": signals,
            "facts":       facts,
            "record_ids":  sorted(set(record_ids)),
            "sources":     sorted(sources),
        })

    return theme_groups + entity_groups


def _union_group(recs: list[dict]) -> tuple:
    """Union entities, events, signals, facts, record_ids, sources from a list of records."""
    entities: set[str]   = set()
    events:   list[dict] = []
    signals:  list[dict] = []
    facts:    list[dict] = []
    record_ids: list[str] = []
    sources:  set[str]   = set()

    seen_events:  set[str] = set()
    seen_signals: set[str] = set()

    for rec in recs:
        record_ids.append(rec.get("id", ""))
        src = rec.get("source", "")
        if src:
            sources.add(src)
        for ent in rec.get("entities", []):
            name = ent.get("name", "").strip()
            if name:
                entities.add(name)
        for ev in rec.get("events", []):
            key = (ev.get("entity", ""), ev.get("event_type", ""), ev.get("text", ""))
            if key not in seen_events:
                seen_events.add(key)
                events.append(ev)
        for sig in rec.get("market_signals", []):
            key = (sig.get("entity", ""), sig.get("direction", ""), sig.get("text", ""))
            if key not in seen_signals:
                seen_signals.add(key)
                signals.append(sig)
        for fact in rec.get("facts", []):
            facts.append(fact)

    return entities, events, signals, facts, record_ids, sources


# ---------------------------------------------------------------------------
# Weighting helpers
# ---------------------------------------------------------------------------

def _weight_group(group: dict, memory: list[dict], cfg: dict) -> int:
    event_w     = int(cfg.get("event_weight", 20))
    signal_w    = int(cfg.get("signal_weight", 15))
    source_w    = int(cfg.get("source_diversity_weight", 5))
    memory_w    = int(cfg.get("memory_hit_weight", 15))

    candidates_from_records: list[dict] = []

    worth_events  = sum(
        1 for c in candidates_from_records if c.get("object_type") == "event" and c.get("worth_storing")
    )
    worth_signals = sum(
        1 for c in candidates_from_records if c.get("object_type") == "market_signal" and c.get("worth_storing")
    )

    # worth_storing from the events/signals directly via candidate scores is not available here;
    # use all events/signals count as a proxy (candidates are per-record, not per-group)
    worth_events  = len([e for e in group["events"]  if e.get("direction") in ("positive", "negative")])
    worth_signals = len([s for s in group["market_signals"] if s.get("direction") in ("bullish", "bearish")])

    group_entities_lower = {e.lower() for e in group["entities"]}
    memory_hits = sum(
        1 for m in memory
        if any(e.lower() in group_entities_lower for e in m.get("triggered_by_entities", []))
    )

    return (
        worth_events  * event_w
        + worth_signals * signal_w
        + len(group["sources"]) * source_w
        + memory_hits * memory_w
    )


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _log_call(log_path: Path, lock: threading.Lock, entry: dict) -> None:
    with lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _format_events(events: list[dict], max_items: int = 10) -> str:
    lines = []
    for ev in events[:max_items]:
        lines.append(f"  - [{ev.get('event_type','?')} / {ev.get('direction','?')}] "
                     f"{ev.get('entity','')}: {ev.get('text','')}")
    return "\n".join(lines) or "  (none)"


def _format_signals(signals: list[dict], max_items: int = 10) -> str:
    lines = []
    for sig in signals[:max_items]:
        lines.append(f"  - [{sig.get('direction','?')} / conf={sig.get('confidence','?')}] "
                     f"{sig.get('entity','')}: {sig.get('text','')}")
    return "\n".join(lines) or "  (none)"


def _format_facts(facts: list[dict], max_items: int = 8) -> str:
    lines = []
    for fact in facts[:max_items]:
        lines.append(f"  - {fact.get('entity','')}: {fact.get('text','')} — {fact.get('value','')}")
    return "\n".join(lines) or "  (none)"


def _format_memory(memory: list[dict], group_entities: set[str], max_items: int = 5) -> str:
    relevant = [
        m for m in memory
        if any(e.lower() in group_entities for e in m.get("triggered_by_entities", []))
    ][:max_items]
    if not relevant:
        return "  (no past context)"
    lines = []
    for m in relevant:
        lines.append(f"  - {m.get('memory_type','?')} | {m.get('title','')}: {m.get('summary','')}")
    return "\n".join(lines)


def _call_llm(
    group: dict,
    memory: list[dict],
    chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str,
) -> dict:
    group_entities_lower = {e.lower() for e in group["entities"]}
    t0 = time.time()

    prompt_vars = {
        "group_name":     group["group_name"],
        "group_type":     group["group_type"],
        "entities":       ", ".join(group["entities"][:20]) or "(none)",
        "events":         _format_events(group["events"]),
        "signals":        _format_signals(group["market_signals"]),
        "facts":          _format_facts(group["facts"]),
        "memory_context": _format_memory(memory, group_entities_lower),
    }

    try:
        raw_result = chain.invoke(prompt_vars)
        parsed     = raw_result.get("parsed")
        raw_msg    = raw_result.get("raw")
        parse_err  = raw_result.get("parsing_error")

        usage      = getattr(raw_msg, "usage_metadata", {}) or {}
        tokens_in  = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        parsed_ok  = parsed is not None and parse_err is None

        extraction   = parsed.model_dump() if parsed_ok else {}
        response_str = parsed.model_dump_json() if parsed_ok else str(parse_err)
    except Exception as e:
        tokens_in, tokens_out = 0, 0
        parsed_ok    = False
        parse_err    = str(e)
        extraction   = {}
        response_str = ""

    latency_ms = round((time.time() - t0) * 1000)

    # reconstruct prompt string for logging
    formatted_prompt = (
        f"Group name: {prompt_vars['group_name']}\n"
        f"Group type: {prompt_vars['group_type']}\n"
        f"Entities: {prompt_vars['entities']}\n\n"
        f"Events:\n{prompt_vars['events']}\n\n"
        f"Signals:\n{prompt_vars['signals']}\n\n"
        f"Facts:\n{prompt_vars['facts']}\n\n"
        f"Memory:\n{prompt_vars['memory_context']}"
    )

    entry: dict = {
        "call_id":    call_id,
        "timestamp":  _now_ist(),
        "layer":      "L5",
        "trigger":    f"group:{group['group_type']}:{group['group_name']}",
        "model":      model_name,
        "prompt":     formatted_prompt,
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    }
    if not parsed_ok and parse_err:
        entry["parse_error"] = str(parse_err)
    _log_call(log_path, lock, entry)

    strength = extraction.get("strength", "?")
    print(f"  [L5] {call_id}: {group['group_name'][:50]} strength={strength} tok={tokens_in}+{tokens_out}")
    return extraction


# ---------------------------------------------------------------------------
# Market regime
# ---------------------------------------------------------------------------

def _derive_market_regime(records: list[dict]) -> dict:
    fii_net_cr    = 0.0
    dii_net_cr    = 0.0
    nifty_dir     = "unknown"
    nifty_change  = 0.0
    signals: list[str] = []
    derived_at = datetime.now(IST).isoformat()

    for rec in records:
        if rec.get("source_type") != "market_snapshot":
            continue
        snap_type = rec.get("metadata", {}).get("snapshot_type", "")
        content   = rec.get("content", "")

        if snap_type == "fii_dii":
            # Format: "FII net=1329.17 cr | DII net=-1958.82 cr"
            m = re.search(r"FII net=(-?[\d.]+)\s*cr", content)
            if m:
                fii_net_cr = float(m.group(1))
                signals.append(f"FII net ₹{fii_net_cr:,.0f} cr")
            m = re.search(r"DII net=(-?[\d.]+)\s*cr", content)
            if m:
                dii_net_cr = float(m.group(1))
                signals.append(f"DII net ₹{dii_net_cr:,.0f} cr")

        elif snap_type == "india_macro":
            # Format: "Change=-0.36%" in Market Breadth line
            m = re.search(r"Change=(-?[\d.]+)%", content)
            if m:
                nifty_change = float(m.group(1))
                nifty_dir    = "positive" if nifty_change >= 0 else "negative"
                signals.append(f"Market breadth change {nifty_change:+.2f}%")

    if fii_net_cr > 0 and nifty_dir == "positive":
        regime = "bull"
    elif fii_net_cr < 0 and nifty_dir == "negative":
        regime = "bear"
    elif fii_net_cr != 0 or nifty_dir != "unknown":
        regime = "sideways"
    else:
        regime = "uncertain"

    return {
        "regime":          regime,
        "fii_net_cr":      fii_net_cr,
        "dii_net_cr":      dii_net_cr,
        "nifty_direction": nifty_dir,
        "nifty_change_pct": nifty_change,
        "signals":         signals,
        "derived_at":      derived_at,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l5_cfg   = manifest.get("layer_5")
    if not l5_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_5' key — re-run L0 first")

    provider      = l5_cfg.get("provider", "openai")
    model         = l5_cfg.get("model") or None
    max_hyp       = int(l5_cfg.get("max_hypotheses", 50))
    max_workers   = int(l5_cfg.get("max_workers", 20))
    min_signals   = int(l5_cfg.get("min_signal_count", 2))
    min_weight    = int(l5_cfg.get("min_weight_score", 30))

    llm        = make_llm(provider=provider, model=model)
    model_name = model or "gpt-5-nano"
    chain      = _PROMPT | llm.with_structured_output(HypothesisOutput, include_raw=True)

    l4_path = output_dir(date) / "L4" / "memory_context.json"
    if not l4_path.exists():
        raise FileNotFoundError(f"L4 output not found: {l4_path} — run L4 first")

    l4_data = json.loads(l4_path.read_text())
    records: list[dict] = l4_data.get("records", [])
    memory:  list[dict] = l4_data.get("memory", [])

    out_dir  = output_dir(date) / "L5"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "llm_calls.jsonl"
    if log_path.exists():
        log_path.unlink()

    print(f"  L5: {len(records)} records, {len(memory)} recalled memories")
    print(f"  Provider: {provider}  Model: {model_name}")

    # Build + score groups
    all_groups = _build_groups(records, memory)
    print(f"  Groups built: {len(all_groups)} total "
          f"(theme={sum(1 for g in all_groups if g['group_type']=='theme_centric')}, "
          f"entity={sum(1 for g in all_groups if g['group_type']=='entity_centric')})")

    for group in all_groups:
        signal_count = len(group["events"]) + len(group["market_signals"])
        group["signal_count"]    = signal_count
        group["source_diversity"] = len(group["sources"])
        group["weight_score"]    = _weight_group(group, memory, l5_cfg)

    # Filter + sort + cap
    filtered = [
        g for g in all_groups
        if g["signal_count"] >= min_signals and g["weight_score"] >= min_weight
    ]
    filtered.sort(key=lambda g: g["weight_score"], reverse=True)
    selected = filtered[:max_hyp]

    print(f"  After filter (min_signals={min_signals}, min_weight={min_weight}): "
          f"{len(filtered)} groups → selecting top {len(selected)}")

    # Market regime (rule-based, no LLM)
    regime = _derive_market_regime(records)
    (out_dir / "market_regime.json").write_text(
        json.dumps(regime, indent=2, ensure_ascii=False)
    )
    print(f"  Market regime: {regime['regime']}")

    # LLM calls
    lock         = threading.Lock()
    call_counter = 0
    jobs: list[tuple[dict, str]] = []
    for group in selected:
        call_counter += 1
        jobs.append((group, f"L5_{date.replace('-', '')}_{call_counter:04d}"))

    hypotheses: list[dict] = []
    hypothesis_counter     = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_job = {
            pool.submit(_call_llm, group, memory, chain, cid, log_path, lock, model_name): (group, cid)
            for group, cid in jobs
        }
        for future in as_completed(future_to_job):
            group, cid = future_to_job[future]
            try:
                extraction = future.result()
            except Exception as e:
                print(f"  [L5] {cid} future error: {e}")
                extraction = {}

            hypothesis_counter += 1
            hyp_id = f"HYP_{date.replace('-', '')}_{hypothesis_counter:04d}"
            hypotheses.append({
                "hypothesis_id":           hyp_id,
                "hypothesis":              extraction.get("hypothesis", ""),
                "beneficiaries":           extraction.get("beneficiaries", []),
                "time_horizon":            extraction.get("time_horizon", ""),
                "strength":                extraction.get("strength", ""),
                "deep_dive_questions":     extraction.get("deep_dive_questions", []),
                "invalidating_conditions": extraction.get("invalidating_conditions", []),
                "group_type":              group["group_type"],
                "group_name":              group["group_name"],
                "entities":                group["entities"],
                "signal_count":            group["signal_count"],
                "source_diversity":        group["source_diversity"],
                "weight_score":            group["weight_score"],
                "record_ids":              group["record_ids"],
                "llm_call_id":             cid,
                "parsed_ok":               bool(extraction.get("hypothesis")),
            })

    # Sort by weight_score descending for consistent output
    hypotheses.sort(key=lambda h: h["weight_score"], reverse=True)

    # Aggregate stats from log
    tokens_in_total  = 0
    tokens_out_total = 0
    parse_failures   = 0
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                e = json.loads(line)
                tokens_in_total  += e.get("tokens_in", 0)
                tokens_out_total += e.get("tokens_out", 0)
                if not e.get("parsed_ok", True):
                    parse_failures += 1
            except Exception:
                pass

    out_path = out_dir / "hypotheses.json"
    out_path.write_text(json.dumps({
        "run_date":   date,
        "run_id":     l4_data.get("run_id", ""),
        "total":      len(hypotheses),
        "hypotheses": hypotheses,
    }, indent=2, ensure_ascii=False))

    (out_dir / "summary.json").write_text(json.dumps({
        "date":               date,
        "total_records":      len(records),
        "total_groups_built": len(all_groups),
        "groups_after_filter": len(filtered),
        "groups_selected":    len(selected),
        "hypotheses_generated": len(hypotheses),
        "parse_failures":     parse_failures,
        "total_tokens_in":    tokens_in_total,
        "total_tokens_out":   tokens_out_total,
        "market_regime":      regime["regime"],
        "max_workers":        max_workers,
    }, indent=2))

    print(f"\n  L5 done: {len(hypotheses)} hypotheses generated from {len(selected)} groups")
    print(f"  Tokens: in={tokens_in_total}, out={tokens_out_total}")
    print(f"  Parse failures: {parse_failures}")
    print(f"  → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
