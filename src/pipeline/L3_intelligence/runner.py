"""
L3 Intelligence Extraction — extracts structured intel from each document using LLM.

Reads:
    output/{date}/L2/filtered_records.json   → quality-filtered records (L2 output)
    output/{date}/run_manifest.json          → layer_3 config (provider, model, thresholds)

Writes:
    output/{date}/L3/enriched_records.json   → same records + entities/facts/events/themes/market_signals
    output/{date}/L3/summary.json            → call counts, token usage, confidence breakdown
    output/{date}/L3/llm_calls.jsonl         → full prompt + response per LLM call

LLM: yes — provider + model from manifest layer_3 config (via src.llm.client.make_llm)
     Long records (content_length >= short_content_chars): one call per record, parallel.
     Short records (<short_content_chars): batched up to batch_size per call, parallel.
     market_snapshot and corporate_action: no LLM, entities derived from metadata.

Module execution order:
    1. Load manifest → layer_3 config; build LangChain chain via make_llm + Pydantic schema
    2. Load L2/filtered_records.json
    3. Partition: skip_types | short (<short_content_chars) | long (>=short_content_chars)
    4. Process skip_types — derive entities from metadata
    5. Pre-assign call IDs; submit all jobs to ThreadPoolExecutor
    6. Collect results, apply to records, write enriched_records.json + summary + llm_calls.jsonl

Usage:
    python -m src.pipeline.L3_intelligence.runner              # today
    python -m src.pipeline.L3_intelligence.runner --date 2026-05-17
"""

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from typing import Literal

from src.config.settings import IST, load_manifest, output_dir, today
from src.llm.client import make_llm


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class Entity(BaseModel):
    name:        str
    type:        Literal["company", "person", "index", "sector", "commodity", "currency"]
    investable:  bool
    signal_type: Literal["direct_subject", "affected_entity", "context_mention"]
    context:     str

class Fact(BaseModel):
    text:   str
    entity: str
    value:  str

class Event(BaseModel):
    text:       str
    entity:     str
    event_type: Literal["earnings", "merger", "regulatory", "macro", "other"]
    direction:  Literal["positive", "negative", "neutral"]

class MarketSignal(BaseModel):
    text:       str
    direction:  Literal["bullish", "bearish", "neutral"]
    entity:     str
    confidence: Literal["high", "medium", "low"]

class DocumentExtraction(BaseModel):
    analysis:              str
    entities:              list[Entity]
    facts:                 list[Fact]
    events:                list[Event]
    themes:                list[str]
    market_signals:        list[MarketSignal]
    extraction_confidence: Literal["high", "medium", "low"]

class BatchExtraction(BaseModel):
    results: list[DocumentExtraction]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SINGLE_PROMPT = ChatPromptTemplate.from_template(
    "You are an investment intelligence analyst for a stock market research system.\n"
    "The team is based in India and invests via NSE/BSE but tracks global markets too.\n\n"
    "Step 1 — analysis: assess what is investment-relevant (companies, sectors, macro, risks, opportunities).\n\n"
    "Step 2 — extract structured signals. Max 10 words per text field. Top 5 per category.\n"
    "Skip anything with no investment relevance.\n\n"
    "Entity extraction rules:\n"
    "  type:\n"
    "    company   → listed or unlisted firm (TCS, Apple, Zomato)\n"
    "    sector    → industry group (Banking, IT, Pharma, EV, Defence)\n"
    "    commodity → raw material / metal / energy (Gold, Crude Oil, Silver, Natural Gas)\n"
    "    currency  → FX pair or currency (USD/INR, Rupee, EUR, DXY)\n"
    "    index     → market index used as benchmark (Nifty 50, S&P 500, Bank Nifty)\n"
    "    person    → individual (CEO, minister, politician, central banker)\n\n"
    "  investable — can an investor directly buy/sell this via exchange or ETF?\n"
    "    company: true | sector: true (via ETFs/funds) | commodity: true (MCX, ETFs)\n"
    "    currency: true (forex) | index: false | person: false\n\n"
    "  signal_type — what role does this entity play in THIS article?\n"
    "    direct_subject  → article is primarily ABOUT this entity\n"
    "                      (earnings report, merger, regulatory action targeting it)\n"
    "    affected_entity → an investor should buy/sell this based on what the article says\n"
    "                      (rate cut → banking stocks benefit; PLI scheme → sector gains)\n"
    "    context_mention → mentioned as background only, not a trading signal\n"
    "                      (Nifty fell 0.5% as context; US markets as backdrop)\n\n"
    "  Examples:\n"
    "    'TCS Q4 results beat estimates by 8%%'\n"
    "      TCS → company, investable=true, direct_subject\n\n"
    "    'RBI cuts repo rate by 25bps'\n"
    "      RBI → person, investable=false, direct_subject\n"
    "      HDFC Bank → company, investable=true, affected_entity\n"
    "      Banking sector → sector, investable=true, affected_entity\n"
    "      Nifty 50 → index, investable=false, context_mention\n\n"
    "    'Modi announces PLI scheme for semiconductors'\n"
    "      Narendra Modi → person, investable=false, direct_subject\n"
    "      Tata Electronics → company, investable=true, affected_entity\n"
    "      Semiconductor sector → sector, investable=true, affected_entity\n\n"
    "    'Gold hits all-time high on safe-haven demand'\n"
    "      Gold → commodity, investable=true, direct_subject\n"
    "      Titan Company → company, investable=true, affected_entity\n\n"
    "Article:\n{content}"
)

_BATCH_PROMPT = ChatPromptTemplate.from_template(
    "You are an investment intelligence analyst. The team is based in India but tracks global markets.\n"
    "Extract structured signals from these {n} headlines in order.\n"
    "Return exactly {n} results. Max 8 words per field. Top 3 per category.\n\n"
    "Entity rules:\n"
    "  type: company | sector | commodity | currency | index | person\n"
    "  investable: true if directly tradeable (stocks, sector ETFs, commodities, forex); "
    "false for indices and persons\n"
    "  signal_type: direct_subject (article is ABOUT it) | "
    "affected_entity (should be traded based on this) | context_mention (background only)\n\n"
    "Headlines:\n{headlines}"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_EXTRACTION = {
    "analysis":              "",
    "entities":              [],
    "facts":                 [],
    "events":                [],
    "themes":                [],
    "market_signals":        [],
    "extraction_confidence": "n/a",
}


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _log_call(log_path: Path, lock: threading.Lock, entry: dict) -> None:
    with lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _safe(text: str) -> str:
    """Escape curly braces in text before passing to ChatPromptTemplate."""
    return text.replace("{", "{{").replace("}", "}}")


def _derive_from_metadata(rec: dict) -> dict:
    ext      = _EMPTY_EXTRACTION.copy()
    stype    = rec.get("source_type", "")
    metadata = rec.get("metadata", {})

    if stype == "corporate_action":
        symbol = metadata.get("symbol", "")
        if symbol:
            ext["entities"] = [{
                "name":        symbol,
                "type":        "company",
                "investable":  True,
                "signal_type": "direct_subject",
                "context":     "bulk/block deal",
            }]

    elif stype == "market_snapshot":
        snap_type = metadata.get("snapshot_type", rec.get("source", ""))
        # india_macro / us_macro / fno are indices used as backdrop
        # fii_dii IS the subject of that snapshot (institutional flow data)
        name_map = {
            "india_macro": "NIFTY 50",
            "fii_dii":     "FII/DII Flows",
            "us_macro":    "US Markets",
            "fno":         "NIFTY Options",
        }
        name  = name_map.get(snap_type, snap_type)
        stype_entity = "direct_subject" if snap_type == "fii_dii" else "context_mention"
        ext["entities"] = [{
            "name":        name,
            "type":        "index",
            "investable":  False,
            "signal_type": stype_entity,
            "context":     "market snapshot",
        }]

    ext["extraction_confidence"] = "derived"
    return ext


# ---------------------------------------------------------------------------
# LLM call wrappers
# ---------------------------------------------------------------------------

def _extract_single(
    rec: dict,
    single_chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str = "",
) -> dict:
    content = _safe(rec.get("content", ""))
    t0 = time.time()

    try:
        raw_result = single_chain.invoke({"content": content})
        parsed     = raw_result.get("parsed")
        raw_msg    = raw_result.get("raw")
        parse_err  = raw_result.get("parsing_error")

        usage      = getattr(raw_msg, "usage_metadata", {}) or {}
        tokens_in  = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        parsed_ok  = parsed is not None and parse_err is None

        extraction = parsed.model_dump() if parsed_ok else _EMPTY_EXTRACTION.copy()
        response_str = parsed.model_dump_json() if parsed_ok else str(parse_err)

    except Exception as e:
        tokens_in, tokens_out = 0, 0
        parsed_ok    = False
        parse_err    = str(e)
        extraction   = _EMPTY_EXTRACTION.copy()
        response_str = ""

    latency_ms = round((time.time() - t0) * 1000)
    entry = {
        "call_id":    call_id,
        "timestamp":  _now_ist(),
        "layer":      "L3",
        "trigger":    rec["id"],
        "model":      model_name,
        "prompt":     rec.get("content", ""),
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
    }
    if not parsed_ok and parse_err:
        entry["parse_error"] = str(parse_err)
    _log_call(log_path, lock, entry)

    conf = extraction.get("extraction_confidence", "?")
    print(f"  [L3] {call_id}: {rec['id']} ({rec.get('content_length', 0)} chars) "
          f"conf={conf} tok={tokens_in}+{tokens_out}")
    return extraction


def _extract_batch(
    batch: list[dict],
    batch_chain,
    call_id: str,
    log_path: Path,
    lock: threading.Lock,
    model_name: str = "",
) -> list[dict]:
    n         = len(batch)
    headlines = "\n".join(
        f"{i + 1}. {_safe(rec.get('title') or rec.get('content', ''))}"
        for i, rec in enumerate(batch)
    )
    t0 = time.time()

    try:
        raw_result = batch_chain.invoke({"n": n, "headlines": headlines})
        parsed     = raw_result.get("parsed")
        raw_msg    = raw_result.get("raw")
        parse_err  = raw_result.get("parsing_error")

        usage      = getattr(raw_msg, "usage_metadata", {}) or {}
        tokens_in  = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)
        parsed_ok  = parsed is not None and parse_err is None

        if parsed_ok:
            extractions = [item.model_dump() for item in parsed.results[:n]]
            while len(extractions) < n:
                extractions.append(_EMPTY_EXTRACTION.copy())
            response_str = parsed.model_dump_json()
        else:
            extractions  = [_EMPTY_EXTRACTION.copy() for _ in batch]
            response_str = str(parse_err)

    except Exception as e:
        tokens_in, tokens_out = 0, 0
        parsed_ok    = False
        parse_err    = str(e)
        extractions  = [_EMPTY_EXTRACTION.copy() for _ in batch]
        response_str = ""

    latency_ms = round((time.time() - t0) * 1000)
    _log_call(log_path, lock, {
        "call_id":    call_id,
        "timestamp":  _now_ist(),
        "layer":      "L3",
        "trigger":    f"batch [{', '.join(r['id'] for r in batch)}]",
        "model":      model_name,
        "prompt":     headlines,
        "response":   response_str,
        "parsed_ok":  parsed_ok,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        **({"parse_error": str(parse_err)} if not parsed_ok else {}),
    })
    print(f"  [L3] {call_id}: batch of {n} short records tok={tokens_in}+{tokens_out}")
    return extractions


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l3_cfg   = manifest.get("layer_3")
    if not l3_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_3' key — re-run L0 first")

    provider    = l3_cfg.get("provider", "openai")
    model       = l3_cfg.get("model") or None
    batch_size  = int(l3_cfg.get("batch_size", 20))
    short_chars = int(l3_cfg.get("short_content_chars", 200))
    max_workers = int(l3_cfg.get("max_workers", 10))
    skip_types  = set(l3_cfg.get("skip_source_types", ["market_snapshot", "corporate_action"]))

    llm          = make_llm(provider=provider, model=model)
    model_name   = model or "gpt-5-nano"
    single_chain = _SINGLE_PROMPT | llm.with_structured_output(DocumentExtraction, include_raw=True)
    batch_chain  = _BATCH_PROMPT  | llm.with_structured_output(BatchExtraction,    include_raw=True)

    l2_path = output_dir(date) / "L2" / "filtered_records.json"
    if not l2_path.exists():
        raise FileNotFoundError(f"L2 output not found: {l2_path} — run L2 first")

    l2_data  = json.loads(l2_path.read_text())
    records: list[dict] = l2_data.get("records", [])

    out_dir  = output_dir(date) / "L3"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "llm_calls.jsonl"
    if log_path.exists():
        log_path.unlink()

    skip_recs  = [r for r in records if r.get("source_type") in skip_types]
    llm_recs   = [r for r in records if r.get("source_type") not in skip_types]
    short_recs = [r for r in llm_recs if r.get("content_length", 0) < short_chars]
    long_recs  = [r for r in llm_recs if r.get("content_length", 0) >= short_chars]

    print(f"  L3: {len(records)} total — skip={len(skip_recs)}, "
          f"batch={len(short_recs)}, individual={len(long_recs)}, workers={max_workers}")
    print(f"  Provider: {provider}  Model: {model or 'env default'}")

    for rec in skip_recs:
        rec.update(_derive_from_metadata(rec))

    lock         = threading.Lock()
    call_counter = 0

    batch_jobs: list[tuple[list[dict], str]] = []
    for i in range(0, len(short_recs), batch_size):
        call_counter += 1
        batch_jobs.append((
            short_recs[i:i + batch_size],
            f"L3_{date.replace('-', '')}_{call_counter:04d}",
        ))

    ind_jobs: list[tuple[dict, str]] = []
    for rec in long_recs:
        call_counter += 1
        ind_jobs.append((rec, f"L3_{date.replace('-', '')}_{call_counter:04d}"))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        batch_futures = {
            pool.submit(_extract_batch, batch, batch_chain, cid, log_path, lock, model_name): batch
            for batch, cid in batch_jobs
        }
        ind_futures = {
            pool.submit(_extract_single, rec, single_chain, cid, log_path, lock, model_name): rec
            for rec, cid in ind_jobs
        }

        for future in as_completed(batch_futures):
            batch = batch_futures[future]
            try:
                for rec, ext in zip(batch, future.result()):
                    rec.update(ext)
            except Exception as e:
                print(f"  [L3] batch future error: {e}")

        for future in as_completed(ind_futures):
            rec = ind_futures[future]
            try:
                rec.update(future.result())
            except Exception as e:
                print(f"  [L3] individual future error: {rec['id']}: {e}")

    # Aggregate stats
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

    confidence_breakdown: dict[str, int] = {}
    for rec in records:
        conf = rec.get("extraction_confidence", "n/a")
        confidence_breakdown[conf] = confidence_breakdown.get(conf, 0) + 1

    out_path = out_dir / "enriched_records.json"
    out_path.write_text(json.dumps({
        "run_date":      date,
        "run_id":        l2_data.get("run_id", ""),
        "total_records": len(records),
        "records":       records,
    }, indent=2, ensure_ascii=False))

    (out_dir / "summary.json").write_text(json.dumps({
        "date":                 date,
        "total_records":        len(records),
        "skip_no_llm":          len(skip_recs),
        "short_batched":        len(short_recs),
        "long_individual":      len(long_recs),
        "total_llm_calls":      call_counter,
        "max_workers":          max_workers,
        "total_tokens_in":      tokens_in_total,
        "total_tokens_out":     tokens_out_total,
        "parse_failures":       parse_failures,
        "confidence_breakdown": confidence_breakdown,
    }, indent=2))

    print(f"\n  L3 done: {len(records)} records enriched via {call_counter} LLM calls "
          f"({max_workers} parallel workers)")
    print(f"  Tokens: in={tokens_in_total}, out={tokens_out_total}")
    print(f"  Parse failures: {parse_failures}")
    print(f"  Confidence: {confidence_breakdown}")
    print(f"  → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
