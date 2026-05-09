"""
context_ext_layer/phaseD_RTP/proxy_mapper.py  —  Phase D, Layer 3 (Research Target Planner)

For each thematic_target produced by Phase B (private companies, sector themes,
macro events, policy signals), an LLM call proposes 3-5 NSE-listed Indian
companies most directly impacted (beneficiaries, competitors, suppliers).

Resolved proxy tickers get merged back into Phase B's `listed_targets` so they
flow through the existing Phase C deep-dive pipeline.

Inputs : output/{date}/phaseB/candidates/candidates_{date}.json (thematic_targets)
Output : output/{date}/phaseD/proxy_mappings/proxy_mappings_{date}.json
         + augments the candidates file in-place with merged listed_targets

Standalone test:
  python context_ext_layer/phaseD_RTP/proxy_mapper.py
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.paths import (
    CANDIDATES_OUTPUT_DIR, PROXY_MAPPINGS_DIR, PROXY_LLM_LOGS_DIR,
)
from context_ext_layer.utils.ticker_extractor import lookup_ticker

_IST = timezone(timedelta(hours=5, minutes=30))

_FUZZY_THRESHOLD  = 82     # same as news_signal_extractor — avoids false matches
_log_lock = threading.Lock()   # guards JSONL log under concurrent writes
_PROXY_SCORE_DAMP = 0.6    # proxy-mapped tickers get theme_relevance × this as score
_MAX_PROXIES_PER_THEME = 5

# ── Pydantic output schema ────────────────────────────────────────────────────

class ProxyTicker(BaseModel):
    company_name: str
    relationship: Literal["beneficiary", "competitor", "supplier", "customer", "proxy"]
    impact:       Literal["positive", "negative", "neutral"]
    confidence:   Literal["high", "medium", "low"]
    reason:       str   # 1-sentence justification


class ProxyMapping(BaseModel):
    proxy_tickers: list[ProxyTicker]


# ── LLM prompt ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an Indian-equity sector analyst.
Given a thematic event, sector trend, macroeconomic event, policy change, or
private/foreign company mentioned in the news, identify 3-5 NSE-listed Indian
companies most directly impacted.

Rules:
- Use ONLY well-known, liquid NSE-listed Indian companies. Use full company
  names recognizable on screener.in (e.g. "Tata Power Co", "Bharat Heavy
  Electricals", "HDFC Bank") — not tickers, not abbreviations.
- relationship:
    beneficiary  : company benefits directly from this theme/event
    competitor   : company competes with the entity (e.g. listed quick-commerce vs Zepto)
    supplier     : company supplies inputs to the entity or theme
    customer     : company is a major customer of the theme/entity
    proxy        : best listed exposure to a non-listed/foreign theme
- impact: direction the listed company's fortunes likely move (positive / negative / neutral)
- confidence:
    high   : direct, well-documented relationship (e.g. NTPC for power demand themes)
    medium : reasonable second-order link
    low    : speculative or weak connection
- reason: one short sentence justifying the link

Return 3-5 proxies. Skip if you cannot find genuinely relevant Indian listed names."""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human",  "Thematic target:\n"
               "  entity_type: {entity_type}\n"
               "  entity_name: {entity_name}\n"
               "  key context: {key_context}\n\n"
               "List the 3-5 NSE-listed Indian companies most directly impacted."),
])


# ── LLM call logger ───────────────────────────────────────────────────────────

_log_file: Path | None = None

def _init_log(run_label: str = "proxy") -> Path:
    global _log_file
    PROXY_LLM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(_IST).strftime("%Y-%m-%d")
    _log_file = PROXY_LLM_LOGS_DIR / f"{run_label}_{today}.jsonl"
    return _log_file


def _log_call(theme: dict, proxies: list, error: str | None = None) -> None:
    if _log_file is None:
        return
    record = {
        "ts":             datetime.now(_IST).isoformat(),
        "entity_type":    theme.get("entity_type"),
        "entity_name":    theme.get("entity_name"),
        "proxies":        proxies,
        "error":          error,
    }
    with _log_lock:
        with _log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_candidates_file() -> Path | None:
    files = sorted(CANDIDATES_OUTPUT_DIR.glob("candidates_*.json"))
    return files[-1] if files else None


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _resolve_proxy(company_name: str) -> tuple[str, str] | None:
    """
    Resolve a free-form company name to an NSE ticker via fuzzy match.
    Returns (ticker, canonical_name) or None if confidence too low.
    """
    if not company_name or len(company_name.strip()) < 3:
        return None
    result = lookup_ticker(company_name, threshold=_FUZZY_THRESHOLD)
    if result:
        return result["ticker"], result["name"]
    return None


def _theme_context(theme: dict) -> str:
    """Pack a theme's key claim(s) into a short context string for the LLM."""
    events = theme.get("key_events", [])
    if not events:
        return theme.get("entity_name", "")
    claims = [e.get("key_claim", "") for e in events[:2] if e.get("key_claim")]
    return " | ".join(claims) or theme.get("entity_name", "")


# ── Core proxy mapping ────────────────────────────────────────────────────────

def map_theme_to_proxies(theme: dict, pipeline) -> list[dict]:
    """LLM call + ticker resolution for one thematic target."""
    try:
        result = pipeline.invoke({
            "entity_type": theme.get("entity_type", "sector"),
            "entity_name": theme.get("entity_name", ""),
            "key_context": _theme_context(theme),
        })
        raw_proxies = result.proxy_tickers
    except Exception as e:
        _log_call(theme, [], error=str(e))
        return []

    _log_call(theme, [p.model_dump() for p in raw_proxies])

    resolved = []
    for p in raw_proxies[:_MAX_PROXIES_PER_THEME]:
        match = _resolve_proxy(p.company_name)
        if not match:
            continue
        ticker, canonical = match
        resolved.append({
            "ticker":       ticker,
            "company":      canonical,
            "company_hint": p.company_name,
            "relationship": p.relationship,
            "impact":       p.impact,
            "confidence":   p.confidence,
            "reason":       p.reason,
            "theme_source":   theme.get("entity_name", ""),
            "theme_type":     theme.get("entity_type", ""),
            "theme_relevance": theme.get("relevance_score", 0.0),
        })
    return resolved


def map_all_themes(
    themes:      list[dict],
    llm=None,
    verbose:     bool = True,
    max_workers: int  = 15,
) -> list[dict]:
    """
    Run proxy mapping on every thematic target. Returns flat list of mappings.
    max_workers: concurrent LLM calls (Phase D typically has 30-50 themes,
    so 15 workers finishes in ~3-5s vs ~30s sequential on gpt-5-nano).
    """
    if not themes:
        return []

    if llm is None:
        from llm.llm_client import make_llm
        llm = make_llm(provider="openai", temperature=0.1)

    log_path = _init_log("proxy")
    if verbose:
        print(f"  Proxy LLM log → {log_path}")
        print(f"  Running {max_workers} concurrent workers on {len(themes)} themes …\n")

    pipeline  = _prompt | llm.with_structured_output(ProxyMapping)
    total     = len(themes)
    results_by_idx: list[list[dict]] = [[] for _ in range(total)]
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(map_theme_to_proxies, theme, pipeline): i
            for i, theme in enumerate(themes)
        }
        for future in as_completed(future_to_idx):
            i     = future_to_idx[future]
            theme = themes[i]
            try:
                proxies = future.result()
            except Exception as e:
                proxies = []
                if verbose:
                    print(f"  ✗  {theme.get('entity_name','?')[:50]}: {e}")
            results_by_idx[i] = proxies
            completed += 1
            if verbose:
                tag    = f"+{len(proxies)} proxies" if proxies else "  none  "
                entity = theme.get("entity_name", "?")[:50]
                print(f"  {completed:3}/{total}  [{theme.get('entity_type','?'):8s}]  {tag}  {entity}")

    # Flatten in original theme order for deterministic output
    mappings: list[dict] = []
    for proxies in results_by_idx:
        mappings.extend(proxies)
    return mappings


# ── Merge proxies into listed_targets ─────────────────────────────────────────

def merge_proxies_into_candidates(
    candidates_data: dict,
    proxy_mappings:  list[dict],
) -> dict:
    """
    Augment listed_targets with proxy-mapped tickers.

    For tickers already in listed_targets: append theme links to a `proxy_links` list.
    For new tickers: append as fresh listed_target with damped score.
    """
    listed = candidates_data.get("listed_targets",
             candidates_data.get("selected_for_phase_c",
             candidates_data.get("candidates", [])))

    # Build index of existing tickers
    by_ticker: dict[str, dict] = {c["ticker"]: c for c in listed}
    new_count    = 0
    linked_count = 0

    # Group proxies by ticker (theme A and theme B might both map to same ticker)
    proxies_by_ticker: dict[str, list[dict]] = {}
    for p in proxy_mappings:
        proxies_by_ticker.setdefault(p["ticker"], []).append(p)

    for ticker, proxies in proxies_by_ticker.items():
        # Pick the highest-confidence proxy entry for this ticker as the primary link
        proxies.sort(key=lambda x: (
            {"high": 3, "medium": 2, "low": 1}.get(x["confidence"], 0),
            x["theme_relevance"],
        ), reverse=True)
        primary = proxies[0]

        link_entries = [{
            "theme_source":   p["theme_source"],
            "theme_type":     p["theme_type"],
            "relationship":   p["relationship"],
            "impact":         p["impact"],
            "confidence":     p["confidence"],
            "reason":         p["reason"],
        } for p in proxies]

        if ticker in by_ticker:
            # Existing candidate — augment with proxy_links
            existing = by_ticker[ticker]
            existing.setdefault("proxy_links", []).extend(link_entries)
            linked_count += 1
        else:
            # New candidate — synthesize a listed_target entry
            damped_score = round(primary["theme_relevance"] * _PROXY_SCORE_DAMP, 2)
            sign = 1 if primary["impact"] == "positive" else (-1 if primary["impact"] == "negative" else 0.5)
            listed.append({
                "ticker":          ticker,
                "company":         primary["company"],
                "score":           damped_score * sign,
                "sector_adj":      0.0,
                "final_score":     damped_score * sign,
                "signal_count":    0,
                "source_count":    1,
                "sources":         ["proxy_mapped"],
                "event_types":     ["proxy_themed"],
                "key_signals":     [],
                "bulk_deal":       None,
                "regime_posture":  candidates_data.get("market_posture", "unknown"),
                "rank":            None,                 # re-ranked below
                "selected_for_phase_c": True,            # forced through
                "proxy_links":     link_entries,
            })
            new_count += 1

    # Re-rank by abs(final_score) so proxies fall in naturally
    listed.sort(key=lambda c: abs(c.get("final_score", 0)), reverse=True)
    for i, c in enumerate(listed, 1):
        c["rank"] = i

    candidates_data["listed_targets"]        = listed
    candidates_data["selected_for_phase_c"]  = listed   # backward-compat alias
    candidates_data["listed_targets_count"]  = len(listed)
    candidates_data["proxy_mapping_summary"] = {
        "total_proxy_mappings": len(proxy_mappings),
        "unique_tickers":       len(proxies_by_ticker),
        "new_tickers_added":    new_count,
        "existing_linked":      linked_count,
    }
    return candidates_data


def save_proxy_mappings(mappings: list[dict]) -> str:
    PROXY_MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    today    = datetime.now(_IST).strftime("%Y-%m-%d")
    out_file = PROXY_MAPPINGS_DIR / f"proxy_mappings_{today}.json"

    out_file.write_text(json.dumps({
        "generated_at": datetime.now(_IST).isoformat(),
        "count":        len(mappings),
        "mappings":     mappings,
    }, ensure_ascii=False, indent=2))
    return str(out_file)


# ── Top-level run ─────────────────────────────────────────────────────────────

def run(provider: str = "openai", verbose: bool = True, max_workers: int = 15) -> dict:
    """Full proxy mapping run: load latest candidates → map themes → merge → save."""
    cand_file = _latest_candidates_file()
    if not cand_file:
        if verbose:
            print("  ✗  No candidates file found — run Phase B first")
        return {}

    cand_data = _load_json(cand_file)
    themes    = cand_data.get("thematic_targets", [])

    if verbose:
        print(f"  Candidates file  : {cand_file.name}")
        print(f"  Thematic targets : {len(themes)}")

    if not themes:
        if verbose:
            print("  –  No thematic_targets to map (Phase B may be old format)")
        return {"mappings_file": None, "merged_candidates": 0}

    from llm.llm_client import make_llm
    llm = make_llm(provider=provider, temperature=0.1)

    mappings = map_all_themes(themes, llm=llm, verbose=verbose, max_workers=max_workers)

    mappings_file = save_proxy_mappings(mappings)
    if verbose:
        print(f"\n  Total proxy mappings : {len(mappings)}")
        print(f"  Mappings saved → {mappings_file}")

    # Merge back into candidates file
    cand_data = merge_proxies_into_candidates(cand_data, mappings)
    cand_file.write_text(json.dumps(cand_data, ensure_ascii=False, indent=2))

    summary = cand_data.get("proxy_mapping_summary", {})
    if verbose:
        print(f"\n  Candidates updated:")
        print(f"    Existing tickers linked : {summary.get('existing_linked', 0)}")
        print(f"    New tickers added       : {summary.get('new_tickers_added', 0)}")
        print(f"    Final listed_targets    : {cand_data.get('listed_targets_count', 0)}")

    return {
        "mappings_file":    mappings_file,
        "candidates_file":  str(cand_file),
        "summary":          summary,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys

    provider = "openai"
    for arg in _sys.argv:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]

    print("=" * 60)
    print("  proxy_mapper — standalone test")
    print(f"  Provider: {provider}")
    print("=" * 60)

    result = run(provider=provider, verbose=True)
    if not result:
        print("\n  No proxy mappings produced.")
