"""
context_ext_layer/phaseB_CS/news_signal_extractor.py  —  Phase B, Module B2

Walks every Phase A text output, calls an LLM (one call per article) to
extract structured company-specific events, then resolves company names
to NSE tickers.

LLM: default Gemini Flash (cheap, fast). Caller can pass any LangChain LLM.
Ticker resolution: uses ticker_extractor.py (NSE symbol list + fuzzy match).

Inputs  : all output/phaseA/ text sources (MC, ET, RSS, newsdata, mediastack,
           youtube, gmail)
Output  : output/phaseB/signals/signals_{date}.json

Standalone test:
  python context_ext_layer/phaseB_CS/news_signal_extractor.py
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    MONEYCONTROL_OUTPUT_DIR, ET_OUTPUT_DIR, RSS_OUTPUT_DIR,
    NEWSDATA_OUTPUT_DIR, MEDIASTACK_OUTPUT_DIR, YOUTUBE_OUTPUT_DIR,
    GMAIL_OUTPUT_DIR, SIGNALS_OUTPUT_DIR, LLM_LOGS_DIR,
)
from context_ext_layer.utils.ticker_extractor import lookup_ticker, extract_tickers

_IST = timezone(timedelta(hours=5, minutes=30))

# ── Source config ─────────────────────────────────────────────────────────────
# Each source: (directory, source_label, credibility_weight, text_extractor_fn)
# weight: how much a signal from this source counts during scoring

_SOURCE_WEIGHT: dict[str, float] = {
    "moneycontrol":   3.0,
    "economic_times": 3.0,
    "rss":            2.0,
    "newsdata_io":    1.5,
    "mediastack":     1.5,
    "gmail":          2.0,
    "youtube":        1.0,
}

_MIN_TEXT_LEN  = 80    # skip items shorter than this (titles only, no content)
_MAX_TEXT_LEN  = 3500  # truncate to keep LLM calls cheap
_LLM_DELAY     = 0.4   # seconds between calls to respect rate limits

# ── Pydantic output schema ────────────────────────────────────────────────────

class NewsSignal(BaseModel):
    ticker_hint: str
    event_type: Literal[
        "earnings_beat", "earnings_miss", "earnings_inline",
        "guidance_raise", "guidance_cut", "dividend", "buyback",
        "management_change", "regulatory_action", "merger_acquisition",
        "analyst_upgrade", "analyst_downgrade", "block_deal",
        "macro_impact", "other",
    ]
    sentiment: Literal["positive", "negative", "neutral"]
    severity:  Literal["high", "medium", "low"]
    key_claim: str

class NewsSignals(BaseModel):
    signals: list[NewsSignal]


# ── LLM prompt template ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a financial analyst specializing in Indian equity markets (NSE/BSE).
Extract company-specific, market-moving events from the news text provided.

Rules:
- Only include events for specific listed companies (NSE/BSE). Ignore Nifty/Sensex index commentary.
- earnings_beat  : actual results above estimates OR clearly positive YoY growth stated
- earnings_miss  : actual results below estimates OR clearly negative YoY growth stated
- earnings_inline: results in line with expectations
- severity=high  : >15% YoY swing, M&A, CEO/MD exit, major regulatory action, fraud
- severity=medium: <15% swing, analyst rating change, guidance update, large block deal
- severity=low   : dividends, bonus shares, routine board meeting, minor disclosures
- Non-English text (Hindi, Telugu, etc.): extract events if company names are identifiable
- Return an empty signals list if no company-specific actionable events are found"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human",  "News text:\n---\n{text}\n---"),
])


# ── LLM call logger ───────────────────────────────────────────────────────────

_log_file: Path | None = None

def _init_log(run_label: str = "signals") -> Path:
    global _log_file
    LLM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(_IST).strftime("%Y-%m-%d")
    _log_file = LLM_LOGS_DIR / f"{run_label}_{today}.jsonl"
    return _log_file

def _log_call(item: dict, signals: list, error: str | None = None) -> None:
    if _log_file is None:
        return
    record = {
        "ts":           datetime.now(_IST).isoformat(),
        "source":       item.get("source", ""),
        "item_title":   item.get("title", "")[:120],
        "item_url":     item.get("url", ""),
        "input_text":   item.get("text", "")[:600],
        "signals":      signals,
        "error":        error,
    }
    with _log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Item collectors — one per source type ────────────────────────────────────

def _collect_mc_et(source: str, dir_path: Path) -> list[dict]:
    """Moneycontrol / Economic Times: articles[] with title + body."""
    items = []
    for f in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            for idx, art in enumerate(data.get("articles", [])):
                title = art.get("title", "")
                body  = art.get("body", "") or art.get("description", "")
                if len(body.strip()) < 40:   # require actual body, not just a title
                    continue
                text  = f"{title}\n\n{body}".strip()
                if len(text) < _MIN_TEXT_LEN:
                    continue
                items.append({
                    "source":        source,
                    "source_file":   str(f),
                    "source_weight": _SOURCE_WEIGHT[source],
                    "item_index":    idx,
                    "title":         title[:120],
                    "url":           art.get("url", ""),
                    "published":     art.get("published", ""),
                    "text":          text[:_MAX_TEXT_LEN],
                })
        except Exception:
            continue
    return items


def _collect_rss(dir_path: Path) -> list[dict]:
    """RSS: individual feed files, each with articles[] containing title + summary."""
    items = []
    for f in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            feed_name = data.get("feed_name", f.stem)
            for idx, art in enumerate(data.get("articles", [])):
                title   = art.get("title", "")
                summary = art.get("summary", "") or art.get("description", "")
                if len(summary.strip()) < 40:  # require actual summary, not just a title
                    continue
                text    = f"{title}\n{summary}".strip()
                if len(text) < _MIN_TEXT_LEN:
                    continue
                items.append({
                    "source":        "rss",
                    "source_file":   str(f),
                    "source_weight": _SOURCE_WEIGHT["rss"],
                    "source_label":  feed_name,
                    "item_index":    idx,
                    "title":         title[:120],
                    "url":           art.get("link", art.get("url", "")),
                    "published":     art.get("published", ""),
                    "text":          text[:_MAX_TEXT_LEN],
                })
        except Exception:
            continue
    return items


def _collect_news_api(source: str, dir_path: Path) -> list[dict]:
    """Newsdata.io / Mediastack: articles[] with title + description."""
    items = []
    for f in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            for idx, art in enumerate(data.get("articles", [])):
                title = art.get("title", "")
                desc  = art.get("description", "") or art.get("content", "")
                if len(desc.strip()) < 40:   # require actual description, not just a title
                    continue
                text  = f"{title}\n{desc}".strip()
                if len(text) < _MIN_TEXT_LEN:
                    continue
                items.append({
                    "source":        source,
                    "source_file":   str(f),
                    "source_weight": _SOURCE_WEIGHT[source],
                    "item_index":    idx,
                    "title":         title[:120],
                    "url":           art.get("link", art.get("url", "")),
                    "published":     art.get("pubDate", art.get("publishedAt", "")),
                    "text":          text[:_MAX_TEXT_LEN],
                })
        except Exception:
            continue
    return items


def _collect_youtube(dir_path: Path) -> list[dict]:
    """YouTube: one JSON per video with a 'transcript' field."""
    items = []
    for f in sorted(dir_path.glob("*.json")):
        try:
            data       = json.loads(f.read_text())
            transcript = data.get("transcript", "")
            if len(transcript) < _MIN_TEXT_LEN:
                continue
            items.append({
                "source":        "youtube",
                "source_file":   str(f),
                "source_weight": _SOURCE_WEIGHT["youtube"],
                "item_index":    0,
                "title":         data.get("video_id", f.stem),
                "url":           data.get("video_url", ""),
                "published":     data.get("extracted_at", ""),
                # Transcripts can be very long — first 3500 chars covers ~10 min
                "text":          transcript[:_MAX_TEXT_LEN],
            })
        except Exception:
            continue
    return items


def _collect_gmail(dir_path: Path) -> list[dict]:
    """Gmail newsletters: body field."""
    items = []
    for f in sorted(dir_path.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            for idx, email in enumerate(data.get("emails", [])):
                body = email.get("body", "") or email.get("snippet", "")
                text = f"{email.get('subject', '')}\n\n{body}".strip()
                if len(text) < _MIN_TEXT_LEN:
                    continue
                items.append({
                    "source":        "gmail",
                    "source_file":   str(f),
                    "source_weight": _SOURCE_WEIGHT["gmail"],
                    "item_index":    idx,
                    "title":         email.get("subject", "")[:120],
                    "url":           "",
                    "published":     email.get("date", ""),
                    "text":          text[:_MAX_TEXT_LEN],
                })
        except Exception:
            continue
    return items


def collect_all_items() -> list[dict]:
    """Collect all text items from every Phase A source directory."""
    items: list[dict] = []
    items += _collect_mc_et("moneycontrol",   MONEYCONTROL_OUTPUT_DIR)
    items += _collect_mc_et("economic_times", ET_OUTPUT_DIR)
    items += _collect_rss(RSS_OUTPUT_DIR)
    items += _collect_news_api("newsdata_io", NEWSDATA_OUTPUT_DIR)
    items += _collect_news_api("mediastack",  MEDIASTACK_OUTPUT_DIR)
    items += _collect_youtube(YOUTUBE_OUTPUT_DIR)
    items += _collect_gmail(GMAIL_OUTPUT_DIR)
    return items


# ── Ticker resolution ─────────────────────────────────────────────────────────

def _resolve_ticker(ticker_hint: str) -> tuple[str | None, str | None]:
    """
    Map a company name/hint from the LLM to an NSE ticker.
    Returns (ticker, company_name) or (None, None) if unresolved.

    Threshold is set high (82) to avoid false positives like
    "indigo" → "Indo-National" or "spicejet" → "Spacenet Enterprises".
    The ALIASES dict in ticker_extractor.py is the safety net for common names.
    """
    if not ticker_hint or len(ticker_hint) < 2:
        return None, None

    # 1. Check aliases first (exact, case-insensitive) — most reliable
    found = extract_tickers(ticker_hint)
    if found:
        return found[0]["ticker"], found[0]["company"]

    # 2. Fuzzy lookup with a high threshold to avoid false positives
    result = lookup_ticker(ticker_hint, threshold=82)
    if result:
        return result["ticker"], result["name"]

    # 3. Unresolved — return None ticker but preserve the hint as company name
    #    so the signal is still recorded (useful for Phase C lookup by name)
    return None, ticker_hint.title()


# ── LLM extraction ────────────────────────────────────────────────────────────

def extract_signals_for_item(item: dict, pipeline) -> list[dict]:
    """
    Run the LLM pipeline on one item. Returns resolved signal dicts with full provenance.
    Build the pipeline once outside this function and pass it in.
    """
    try:
        result  = pipeline.invoke({"text": item["text"]})
        signals = result.signals
    except Exception as e:
        _log_call(item, [], error=str(e))
        return [{"_error": str(e), "_item_title": item["title"]}]

    _log_call(item, [s.model_dump() for s in signals])

    resolved = []
    for sig in signals:
        ticker, company = _resolve_ticker(sig.ticker_hint)
        resolved.append({
            "source":         item["source"],
            "source_file":    item["source_file"],
            "source_weight":  item["source_weight"],
            "source_label":   item.get("source_label", item["source"]),
            "item_title":     item["title"],
            "item_url":       item.get("url", ""),
            "item_published": item.get("published", ""),
            "ticker_hint":    sig.ticker_hint,
            "ticker":         ticker,
            "company":        company,
            "event_type":     sig.event_type,
            "sentiment":      sig.sentiment,
            "severity":       sig.severity,
            "key_claim":      sig.key_claim,
        })
    return resolved


def extract_all_signals(llm=None, verbose: bool = True) -> dict:
    """
    Walk all Phase A sources, call LLM per item, aggregate signals.
    Returns a result dict ready for save_signals().
    """
    if llm is None:
        from llm.llm_client import make_llm
        llm = make_llm(provider="gemini", temperature=0.05)

    model_name = getattr(getattr(llm, "model_name", None) or
                         getattr(llm, "model", None), "__str__", str)()

    log_path = _init_log("signals")
    if verbose:
        print(f"  LLM call log → {log_path}")

    items = collect_all_items()
    if verbose:
        print(f"  Collected {len(items)} items from Phase A sources")

    pipeline = _prompt | llm.with_structured_output(NewsSignals)

    all_signals:  list[dict] = []
    processed_items: list[dict] = []
    failed = skipped = 0

    for i, item in enumerate(items):
        sigs = extract_signals_for_item(item, pipeline)
        time.sleep(_LLM_DELAY)

        n = len([s for s in sigs if "_error" not in s])
        if verbose:
            tag = f"+{n} sig" if n else "  —  "
            print(f"  {i+1:4}/{len(items)}  [{item['source'][:2].upper()}]  {tag}  {item['title'][:55]}")

        has_error = any("_error" in s for s in sigs)
        if has_error:
            failed += 1
            sigs = []

        # Build per-item record with full context
        item_record = {
            "source":        item["source"],
            "source_file":   item["source_file"],
            "source_weight": item["source_weight"],
            "item_index":    item["item_index"],
            "title":         item["title"],
            "url":           item.get("url", ""),
            "published":     item.get("published", ""),
            "signal_count":  len(sigs),
            "signals":       sigs,
        }
        processed_items.append(item_record)
        all_signals.extend(sigs)

    items_with_signals = sum(1 for it in processed_items if it["signal_count"] > 0)

    return {
        "generated_at": datetime.now(_IST).isoformat(),
        "llm_model":    model_name,
        "llm_log_file": str(log_path),
        "phase_a_dirs": {
            "moneycontrol":   str(MONEYCONTROL_OUTPUT_DIR),
            "economic_times": str(ET_OUTPUT_DIR),
            "rss":            str(RSS_OUTPUT_DIR),
            "newsdata_io":    str(NEWSDATA_OUTPUT_DIR),
            "mediastack":     str(MEDIASTACK_OUTPUT_DIR),
            "youtube":        str(YOUTUBE_OUTPUT_DIR),
            "gmail":          str(GMAIL_OUTPUT_DIR),
        },
        "stats": {
            "total_items_scanned":  len(items),
            "items_with_signals":   items_with_signals,
            "total_signals":        len(all_signals),
            "items_failed_llm":     failed,
        },
        "items": processed_items,
    }


def save_signals(result: dict) -> str:
    """Save the signals result dict to output/phaseB/signals/."""
    SIGNALS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    out_file = SIGNALS_OUTPUT_DIR / f"signals_{today}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return str(out_file)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    from collections import Counter

    full_run = "--full" in _sys.argv
    provider = "gemini"
    for arg in _sys.argv:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]

    print("=" * 60)
    print("  news_signal_extractor — standalone test")
    mode = "FULL RUN" if full_run else "SAMPLE (10 articles)"
    print(f"  Mode: {mode}  |  Provider: {provider}")
    print("=" * 60)

    all_items = collect_all_items()
    print(f"\nTotal items collected: {len(all_items)}")
    counts = Counter(it["source"] for it in all_items)
    for src, cnt in sorted(counts.items()):
        print(f"  {src:20s}: {cnt} items")

    if full_run:
        sample = all_items
    else:
        sample = (
            [it for it in all_items if it["source"] in ("moneycontrol", "economic_times")][:5]
            + [it for it in all_items if it["source"] == "rss"][:5]
        )

    log_path = _init_log("signals_test" if not full_run else "signals_full")
    print(f"\nLLM call log  → {log_path}")
    print(f"Running LLM ({provider}) on {len(sample)} item(s)...\n")

    from llm.llm_client import make_llm
    llm      = make_llm(provider=provider, temperature=0.05)
    pipeline = _prompt | llm.with_structured_output(NewsSignals)

    processed_items: list[dict] = []
    all_signals:     list[dict] = []
    failed = 0

    for item in sample:
        sigs = extract_signals_for_item(item, pipeline)
        has_error = any("_error" in s for s in sigs)
        if has_error:
            failed += 1
            sigs = []
        else:
            sigs = [s for s in sigs if "_error" not in s]
        all_signals.extend(sigs)

        item_record = {
            "source":        item["source"],
            "source_file":   item["source_file"],
            "source_weight": item["source_weight"],
            "item_index":    item["item_index"],
            "title":         item["title"],
            "url":           item.get("url", ""),
            "published":     item.get("published", ""),
            "signal_count":  len(sigs),
            "signals":       sigs,
        }
        processed_items.append(item_record)

        print(f"  [{item['source']}] {item['title'][:65]}")
        if sigs:
            for s in sigs:
                ticker = s.get("ticker") or "?unresolved?"
                print(f"    → {ticker:22s}  {s.get('event_type','?'):20s}  "
                      f"[{s.get('sentiment','?')}/{s.get('severity','?')}]  "
                      f"{s.get('key_claim','')[:55]}")
        else:
            print("    → no signals extracted")
        time.sleep(_LLM_DELAY)

    model_name      = str(getattr(llm, "model", getattr(llm, "model_name", provider)))
    items_with_sigs = sum(1 for it in processed_items if it["signal_count"] > 0)
    result = {
        "generated_at": datetime.now(_IST).isoformat(),
        "llm_model":    model_name,
        "llm_log_file": str(log_path),
        "test_run":     not full_run,
        "phase_a_dirs": {
            "moneycontrol":   str(MONEYCONTROL_OUTPUT_DIR),
            "economic_times": str(ET_OUTPUT_DIR),
            "rss":            str(RSS_OUTPUT_DIR),
            "newsdata_io":    str(NEWSDATA_OUTPUT_DIR),
            "mediastack":     str(MEDIASTACK_OUTPUT_DIR),
            "youtube":        str(YOUTUBE_OUTPUT_DIR),
            "gmail":          str(GMAIL_OUTPUT_DIR),
        },
        "stats": {
            "total_items_scanned":  len(sample),
            "items_with_signals":   items_with_sigs,
            "total_signals":        len(all_signals),
            "items_failed_llm":     failed,
        },
        "items": processed_items,
    }

    saved = save_signals(result)
    print(f"\n  Total signals extracted : {len(all_signals)}")
    print(f"  Items with signals      : {items_with_sigs}/{len(sample)}")
    print(f"  LLM failures            : {failed}")
    print(f"  Signals saved → {saved}")
    print(f"  LLM log saved → {log_path}")
    if not full_run:
        print("\n  Tip: python news_signal_extractor.py --full          → process all items")
        print("       python run_phase_b.py                           → full Phase B pipeline")
