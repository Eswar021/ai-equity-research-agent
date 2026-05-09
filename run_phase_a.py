"""
run_phase_a.py — Phase A: Broad Market Discovery

Reads all config from config/phase_a.yaml and runs every data collector.
No state tracked — each run fetches fresh data as of right now.

Ideal run time: around market close (3:30 PM IST) or just after.

  ⚠ F&O data is a live option-chain snapshot — it returns empty data
    outside market hours (9:15 AM – 3:30 PM IST, weekdays).

Usage
─────
  python run_phase_a.py              # full run
  python run_phase_a.py --skip-yt   # skip YouTube (use when API quota is tight)
"""

import sys
import yaml
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

sys.path.append(str(Path(__file__).parent))

_IST     = timezone(timedelta(hours=5, minutes=30))
_CFG     = yaml.safe_load((Path(__file__).parent / "config" / "phase_a.yaml").read_text())


# ── Helper ────────────────────────────────────────────────────────────────────

def _run(label: str, fn, *args, **kwargs) -> list[str]:
    """Call fn, print result, return list of file paths. Never crashes the run."""
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, list):
            paths = [r for r in result if r]
            print(f"  ✓  {label}: {len(paths)} file(s)")
            return paths
        elif result:
            print(f"  ✓  {label}: {Path(str(result)).name}")
            return [str(result)]
        else:
            print(f"  -  {label}: nothing returned")
            return []
    except Exception as e:
        print(f"  ✗  {label}: {e}")
        return []


# ── Main ──────────────────────────────────────────────────────────────────────

def run(skip_yt: bool = False) -> dict:
    start = datetime.now(_IST)
    print(f"\n{'═'*60}")
    print(f"  Phase A — Broad Market Discovery")
    print(f"  {start.strftime('%d %b %Y  %I:%M %p IST')}")
    print(f"{'═'*60}")

    all_files: list[str] = []

    # ── 1. Market snapshot (structured numbers) ───────────────────────────────
    print("\n── Market Snapshot ──────────────────────────────────────")
    from context_ext_layer.phaseA_BMD.india_macro import save_macro_snapshot
    from context_ext_layer.phaseA_BMD.us_macro    import save_us_macro
    from context_ext_layer.phaseA_BMD.fii_dii     import save_fii_dii
    from context_ext_layer.phaseA_BMD.bulk_deals  import save_bulk_deals
    from context_ext_layer.phaseA_BMD.fno_data    import save_fno_snapshot

    all_files += _run("India macro  (Nifty PE/PB, sector %, commodities, rates)", save_macro_snapshot)
    all_files += _run("US macro     (FRED: Fed rate, 10Y yield, CPI)",             save_us_macro)
    all_files += _run("FII/DII      (today's buy/sell/net in ₹ crore)",            save_fii_dii)
    all_files += _run("Bulk deals   (today's NSE bulk + block deals)",              save_bulk_deals)

    for symbol in _CFG.get("fno", {}).get("symbols", ["NIFTY", "BANKNIFTY"]):
        all_files += _run(f"F&O {symbol:10s} (PCR, max pain, ATM IV, OI chain)", save_fno_snapshot, symbol)

    # ── 2. News articles — MC + ET (full article body) ────────────────────────
    print("\n── News Articles  (Moneycontrol + Economic Times) ───────")
    from context_ext_layer.phaseA_BMD.moneycontrol   import save_category as mc_save
    from context_ext_layer.phaseA_BMD.economic_times import save_category as et_save

    mc_cfg = _CFG.get("moneycontrol", {})
    for cat in mc_cfg.get("categories", []):
        all_files += _run(
            f"MC/{cat}",
            mc_save, cat,
            days_back=mc_cfg.get("days_back", 1),
            max_pages=mc_cfg.get("max_pages", 5),
        )

    et_cfg = _CFG.get("economic_times", {})
    for cat in et_cfg.get("categories", []):
        all_files += _run(
            f"ET/{cat}",
            et_save, cat,
            days_back=et_cfg.get("days_back", 1),
            max_pages=et_cfg.get("max_pages", 5),
        )

    # ── 3. RSS feeds (headlines + summaries) ──────────────────────────────────
    print("\n── RSS Feeds  (headlines + summaries, no paywall) ───────")
    from context_ext_layer.phaseA_BMD.rss import save_all_feeds

    feeds = _CFG.get("rss_feeds", {})
    all_files += _run(f"RSS feeds ({len(feeds)} configured)", save_all_feeds, feeds)

    # ── 4. News APIs (query-based, title + description only) ──────────────────
    print("\n── News APIs  (query-based, title + description) ────────")
    from context_ext_layer.phaseA_BMD.newsdata_io import save_news as nd_save
    from context_ext_layer.phaseA_BMD.mediastack  import save_news as ms_save

    for q in _CFG.get("newsdata_io", {}).get("queries", []):
        all_files += _run(f"Newsdata.io  \"{q[:40]}\"", nd_save, q)

    for q in _CFG.get("mediastack", {}).get("queries", []):
        all_files += _run(f"Mediastack   \"{q[:40]}\"", ms_save, q)

    # ── 5. Gmail newsletters ──────────────────────────────────────────────────
    print("\n── Gmail Newsletters ─────────────────────────────────────")
    from context_ext_layer.phaseA_BMD.gmail import save_newsletters

    gmail_cfg = _CFG.get("gmail", {})
    limit     = gmail_cfg.get("limit", 5)
    for src in gmail_cfg.get("sources", []):
        label = src["label"]
        kw    = {k: v for k, v in src.items() if k != "label"}
        all_files += _run(f"Gmail: {label}", save_newsletters, **kw, limit=limit)

    # ── 6. YouTube transcripts ────────────────────────────────────────────────
    print("\n── YouTube Transcripts  (last N days, Shorts excluded) ──")
    if skip_yt:
        print("  –  Skipped  (--skip-yt flag set)")
    else:
        from context_ext_layer.phaseA_BMD.yt_transcript import save_all_channels

        yt_cfg   = _CFG.get("youtube", {})
        channels = yt_cfg.get("channels", [])
        days     = yt_cfg.get("days_back", 2)
        enabled  = [ch for ch in channels if ch.get("enabled", True)]
        all_files += _run(
            f"YouTube ({len(enabled)} enabled channel(s), last {days} day(s))",
            save_all_channels, channels, days,
        )

    # ── Layer 1 bundler — assemble Layer 2 contract files ────────────────────
    print("\n── Layer 1 Bundle ───────────────────────────────────────")
    from context_ext_layer.layer1_bundler import bundle as bundle_layer1
    try:
        b = bundle_layer1()
        print(f"  ✓  raw_context_bundle.json  ({b['total_items']} items, "
              f"{b['modules_ok']} modules ok, {b['modules_empty']} empty)")
        print(f"  ✓  raw_source_records.json")
        print(f"  ✓  collection_status.json")
        print(f"  ✓  data_freshness_report.json")
        print(f"  Output  →  output/layer1/")
    except Exception as e:
        print(f"  ✗  Layer 1 bundle failed: {e}")
        b = {}

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now(_IST) - start).seconds
    print(f"\n{'═'*60}")
    print(f"  Done in {elapsed}s — {len(all_files)} file(s) collected")
    print(f"  Phase A →  output/phaseA/")
    print(f"  Layer 1 →  output/layer1/")
    print(f"{'═'*60}\n")

    return {"files": all_files, "total": len(all_files), "layer1_bundle": b}


if __name__ == "__main__":
    skip_yt = "--skip-yt" in sys.argv
    run(skip_yt=skip_yt)
