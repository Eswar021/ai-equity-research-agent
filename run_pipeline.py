"""
run_pipeline.py — Full end-to-end stock research pipeline

  Phase A → Phase B → Phase D (proxy_mapper)
                    → Phase C (deep dive on augmented listed_targets)
                    → Phase E (evidence cards)
                    → Phase F (analyst views)
                    → Phase G (final report)

Usage:
  python run_pipeline.py                        # full E2E
  python run_pipeline.py --skip-phase-a         # reuse today's collected data
  python run_pipeline.py --skip-to D            # only run from Phase D onwards
  python run_pipeline.py --skip-to F            # only re-run analyst + report
  python run_pipeline.py --provider openai      # default; gemini also supported
  python run_pipeline.py --ticker BHEL.NS       # single-ticker E2E (skips phase A)
  python run_pipeline.py --skip-screener        # skip slow screener.in scrape
  python run_pipeline.py --skip-yt              # skip YouTube collection
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

sys.path.append(str(Path(__file__).parent))

_IST = timezone(timedelta(hours=5, minutes=30))

# Phases in execution order
_PHASES = ["A", "B", "D", "C", "E", "F", "G"]


def _phase_index(phase_letter: str) -> int:
    try:
        return _PHASES.index(phase_letter.upper())
    except ValueError:
        return -1


def _should_run(phase: str, skip_to: str | None, explicit_skips: set[str]) -> bool:
    if phase in explicit_skips:
        return False
    if skip_to and _phase_index(phase) < _phase_index(skip_to):
        return False
    return True


def _banner(label: str, ch: str = "═") -> None:
    print(f"\n{ch * 70}")
    print(f"  {label}")
    print(f"{ch * 70}")


def run(
    skip_phase_a:    bool = False,
    skip_yt:         bool = False,
    skip_signals:    bool = False,
    skip_screener:   bool = False,
    skip_to:         str | None = None,
    single_ticker:   str | None = None,
    provider:        str = "openai",
    max_workers:     int = 25,
) -> dict:
    start = datetime.now(_IST)
    explicit_skips: set[str] = set()
    if skip_phase_a or single_ticker:
        explicit_skips.add("A")

    _banner(f"Stock Research Pipeline — {start.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"  Provider: {provider}")
    if skip_to:        print(f"  Skip-to: {skip_to.upper()}")
    if explicit_skips: print(f"  Explicit skips: {sorted(explicit_skips)}")
    if single_ticker:  print(f"  Single ticker: {single_ticker}")

    results: dict = {}

    # ── Phase A: Broad Market Discovery ───────────────────────────────────────
    if _should_run("A", skip_to, explicit_skips):
        _banner("Phase A — Broad Market Discovery", "─")
        from run_phase_a import run as run_a
        results["phase_a"] = run_a(skip_yt=skip_yt)
    else:
        print("\n  ─  Phase A skipped")

    # ── Phase B: Market Intelligence (Layer 2) ────────────────────────────────
    if _should_run("B", skip_to, explicit_skips):
        _banner("Phase B — Market Intelligence", "─")
        from run_phase_b import run as run_b
        results["phase_b"] = run_b(skip_signals=skip_signals, provider=provider, max_workers=max_workers)
    else:
        print("\n  ─  Phase B skipped")

    # ── Phase D: Proxy Mapper (Layer 3) ───────────────────────────────────────
    if _should_run("D", skip_to, explicit_skips):
        _banner("Phase D — Proxy Mapper (themes → listed proxies)", "─")
        from context_ext_layer.phaseD_RTP.proxy_mapper import run as run_d
        results["phase_d"] = run_d(provider=provider, verbose=True)
    else:
        print("\n  ─  Phase D skipped")

    # ── Phase C: Company Deep Dive (Layer 4, after augmentation) ──────────────
    if _should_run("C", skip_to, explicit_skips):
        _banner("Phase C — Company Deep Dive", "─")
        from run_phase_c import run as run_c
        ticker_list = [single_ticker] if single_ticker else None
        results["phase_c"] = run_c(tickers=ticker_list, skip_screener=skip_screener)
    else:
        print("\n  ─  Phase C skipped")

    # ── Phase E: Evidence Card Builder (Layer 5) ──────────────────────────────
    if _should_run("E", skip_to, explicit_skips):
        _banner("Phase E — Evidence Card Builder", "─")
        from context_ext_layer.phaseE_EB.evidence_card_builder import run as run_e
        ticker_list = [single_ticker] if single_ticker else None
        results["phase_e"] = run_e(tickers=ticker_list, verbose=True)
    else:
        print("\n  ─  Phase E skipped")

    # ── Phase F: Stock Analyst (Layer 6) ──────────────────────────────────────
    if _should_run("F", skip_to, explicit_skips):
        _banner("Phase F — Stock Analyst", "─")
        from context_ext_layer.phaseF_AA.stock_analyst import run as run_f
        ticker_list = [single_ticker] if single_ticker else None
        results["phase_f"] = run_f(tickers=ticker_list, provider=provider, verbose=True)
    else:
        print("\n  ─  Phase F skipped")

    # ── Phase G: Final Report (Layer 7) ───────────────────────────────────────
    if _should_run("G", skip_to, explicit_skips):
        _banner("Phase G — Report Synthesizer", "─")
        from context_ext_layer.phaseG_FR.report_synthesizer import synthesize
        results["phase_g"] = synthesize()
    else:
        print("\n  ─  Phase G skipped")

    elapsed = (datetime.now(_IST) - start).seconds
    _banner(f"Pipeline complete — {elapsed}s")
    if "phase_g" in results and "md_file" in results["phase_g"]:
        counts = results["phase_g"].get("counts", {})
        print(f"  Tickers analyzed : {counts.get('tickers_analyzed', 0)}")
        print(f"  Invests / Watches / Avoids : "
              f"{counts.get('invests',0)} / {counts.get('watches',0)} / {counts.get('avoids',0)}")
        print(f"  Report → {results['phase_g']['md_file']}")
    print()

    return results


if __name__ == "__main__":
    skip_phase_a  = "--skip-phase-a" in sys.argv or "--skip-a" in sys.argv
    skip_yt       = "--skip-yt" in sys.argv
    skip_signals  = "--skip-signals" in sys.argv
    skip_screener = "--skip-screener" in sys.argv

    skip_to       = None
    provider      = "openai"
    single_ticker = None
    max_workers   = 25

    for i, arg in enumerate(sys.argv):
        if arg.startswith("--skip-to="):
            skip_to = arg.split("=", 1)[1]
        elif arg == "--skip-to" and i + 1 < len(sys.argv):
            skip_to = sys.argv[i + 1]
        elif arg.startswith("--provider="):
            provider = arg.split("=", 1)[1]
        elif arg == "--provider" and i + 1 < len(sys.argv):
            provider = sys.argv[i + 1]
        elif arg.startswith("--ticker="):
            single_ticker = arg.split("=", 1)[1]
        elif arg == "--ticker" and i + 1 < len(sys.argv):
            single_ticker = sys.argv[i + 1]
        elif arg.startswith("--workers="):
            max_workers = int(arg.split("=", 1)[1])
        elif arg == "--workers" and i + 1 < len(sys.argv):
            max_workers = int(sys.argv[i + 1])

    run(
        skip_phase_a=skip_phase_a,
        skip_yt=skip_yt,
        skip_signals=skip_signals,
        skip_screener=skip_screener,
        skip_to=skip_to,
        single_ticker=single_ticker,
        provider=provider,
        max_workers=max_workers,
    )
