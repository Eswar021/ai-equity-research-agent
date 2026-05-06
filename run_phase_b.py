"""
run_phase_b.py — Phase B: Candidate Selection

Runs B1 → B2 → B3 in sequence:
  B1. market_regime.py      — rule-based macro regime (no LLM)
  B2. news_signal_extractor — LLM extracts events from all Phase A text
  B3. candidate_scorer      — ranks tickers by signal strength + regime fit

Reads all config from Phase A outputs (no separate config file needed).

Usage
─────
  python run_phase_b.py                  # full run (all sources, LLM)
  python run_phase_b.py --skip-signals   # skip LLM step, use last signals file
  python run_phase_b.py --provider openai
  python run_phase_b.py --provider lmstudio
"""

import sys
import json 
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

sys.path.append(str(Path(__file__).parent))

_IST = timezone(timedelta(hours=5, minutes=30))


# ── Helper ────────────────────────────────────────────────────────────────────

def _run(label: str, fn, *args, **kwargs):
    """Call fn, print result/error. Returns the function's return value."""
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, str):
            print(f"  ✓  {label}: {Path(result).name}")
        elif isinstance(result, dict):
            print(f"  ✓  {label}")
        elif isinstance(result, list):
            print(f"  ✓  {label}: {len(result)} item(s)")
        else:
            print(f"  ✓  {label}")
        return result
    except Exception as e:
        print(f"  ✗  {label}: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run(skip_signals: bool = False, provider: str = "openai") -> dict:
    start = datetime.now(_IST)
    print(f"\n{'═'*60}")
    print(f"  Phase B — Candidate Selection")
    print(f"  {start.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"{'═'*60}")

    # ── B1. Market Regime ─────────────────────────────────────────────────────
    print("\n── B1. Market Regime (rule-based) ───────────────────────")
    from context_ext_layer.phaseB_CS.market_regime import compute_regime, save_regime

    regime      = _run("Computing regime", compute_regime)
    regime_file = _run("Saving regime",    save_regime)

    if regime:
        rd = regime.get("raw_data", {})
        sg = regime.get("signals", {})
        print(f"\n  Posture        : {regime.get('market_posture','?').upper()}")
        print(f"  Breadth (A/D)  : {sg.get('breadth','?')}  (ratio={rd.get('ad_ratio')})")
        print(f"  FII net        : {sg.get('fii','?')}  (₹{rd.get('fii_net_cr')} cr)")
        print(f"  VIX India      : {sg.get('vix','?')}  ({rd.get('vix_india')})")
        print(f"  Crude Brent    : {sg.get('crude','?')}  (${rd.get('crude_brent_usd')})")
        print(f"  USD/INR        : {sg.get('usd_inr','?')}  ({rd.get('usd_inr')})")
        print(f"  Favoured       : {regime.get('sectors',{}).get('favored',[])}")
        print(f"  Avoid          : {regime.get('sectors',{}).get('avoid',[])}")

    # ── B2. News Signal Extraction (LLM) ──────────────────────────────────────
    print("\n── B2. News Signal Extraction (LLM) ─────────────────────")
    from context_ext_layer.phaseB_CS.news_signal_extractor import (
        extract_all_signals, save_signals, collect_all_items,
    )
    from config.paths import SIGNALS_OUTPUT_DIR

    signals_data  = None
    signals_file  = None

    if skip_signals:
        # Use the most recent signals file instead of running LLM
        from config.paths import SIGNALS_OUTPUT_DIR
        existing = sorted(SIGNALS_OUTPUT_DIR.glob("signals_*.json"))
        if existing:
            signals_file = str(existing[-1])
            with open(signals_file) as f:
                signals_data = json.load(f)
            print(f"  –  Skipped (--skip-signals). Using: {Path(signals_file).name}")
            st = signals_data.get("stats", {})
            print(f"     Items: {st.get('total_items_scanned',0)}  "
                  f"Signals: {st.get('total_signals',0)}")
        else:
            print("  ✗  No existing signals file found — cannot skip")
    else:
        # Collect items first so we can show the breakdown
        items = collect_all_items()
        from collections import Counter
        counts = Counter(it["source"] for it in items)
        print(f"  Items collected: {len(items)}")
        for src, cnt in sorted(counts.items()):
            print(f"    {src:20s}: {cnt}")

        # Build LLM and run extraction
        from llm.llm_client import make_llm
        llm = make_llm(provider=provider, temperature=0.05)
        print(f"LLM Provider: {llm.__class__.__name__}")
        print(f"Model: {getattr(llm, 'model_name', 'N/A')}")
        
        
        print(f"\n  Running LLM ({provider}) on {len(items)} items...")
        signals_data = _run("Signal extraction", extract_all_signals,
                            llm=llm, verbose=True)

        if signals_data:
            signals_file = _run("Saving signals", save_signals, signals_data)
            st = signals_data.get("stats", {})
            print(f"\n  Items scanned    : {st.get('total_items_scanned',0)}")
            print(f"  Items w/ signals : {st.get('items_with_signals',0)}")
            print(f"  Total signals    : {st.get('total_signals',0)}")
            print(f"  LLM failures     : {st.get('items_failed_llm',0)}")

    # ── B3. Candidate Scoring ─────────────────────────────────────────────────
    print("\n── B3. Candidate Scoring ────────────────────────────────")
    from context_ext_layer.phaseB_CS.candidate_scorer import (
        load_bulk_deals, _build_bulk_signals, score_candidates, save_candidates,
    )
    from config.paths import BULK_DEALS_OUTPUT_DIR

    scored          = {}
    candidates_file = None

    if signals_data and regime:
        deals     = _run("Loading bulk deals", load_bulk_deals)
        deals     = deals or []
        bulk_sigs = _build_bulk_signals(deals)

        bulk_file = str(sorted(BULK_DEALS_OUTPUT_DIR.glob("*.json"))[-1]) \
                    if any(BULK_DEALS_OUTPUT_DIR.glob("*.json")) else None

        scored = _run("Scoring candidates", score_candidates,
                      signals_data, regime, bulk_sigs)
        scored = scored or {}
        selected = scored.get("selected", [])

        if scored:
            candidates_file = _run("Saving candidates", save_candidates,
                                   scored, regime,
                                   signals_file or "", bulk_file)
    else:
        print("  –  Skipped (missing signals or regime data)")

    # ── Summary ───────────────────────────────────────────────────────────────
    selected = scored.get("selected", []) if scored else []
    elapsed  = (datetime.now(_IST) - start).seconds
    print(f"\n{'═'*60}")
    print(f"  Phase B complete — {elapsed}s")
    print(f"  Market posture   : {regime.get('market_posture','?').upper() if regime else '?'}")
    print(f"  All scored       : {len(scored.get('all_candidates', []))}")
    print(f"  Selected (Phase C): {len(selected)}")
    print(f"{'═'*60}")

    if selected:
        print(f"\n  {'Rank':4}  {'Ticker':20}  {'Score':7}  {'Sigs':5}  {'Srcs':5}  Top Event")
        print(f"  {'─'*70}")
        for c in selected[:10]:
            score_s = f"{c['final_score']:+.1f}"
            etype   = c['event_types'][0] if c.get('event_types') else '—'
            print(f"  {c['rank']:4}  {c['ticker']:20}  {score_s:7}  "
                  f"{c['signal_count']:5}  {c['source_count']:5}  {etype}")
            if c.get("key_signals"):
                print(f"        ↳ {c['key_signals'][0].get('key_claim','')[:65]}")

    if candidates_file:
        print(f"\n  Output → {candidates_file}")
    print()

    return {
        "regime":          regime,
        "regime_file":     regime_file,
        "signals_file":    signals_file,
        "candidates":      selected,
        "candidates_file": candidates_file,
    }


if __name__ == "__main__":
    skip_signals = "--skip-signals" in sys.argv

    provider = "openai"
    for arg in sys.argv:
        if arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
        elif arg == "--provider" and sys.argv.index(arg) + 1 < len(sys.argv):
            provider = sys.argv[sys.argv.index(arg) + 1]

    run(skip_signals=skip_signals, provider=provider)
