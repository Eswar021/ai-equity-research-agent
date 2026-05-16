"""
L1 Scraping — collects raw data from all configured sources into one flat file.

Reads:
    output/{date}/run_manifest.json   → layer_1 config (which sources, limits, queries)

Writes:
    output/{date}/L1/raw_records.json → all scraped records, flat list (input to L2)
    output/{date}/L1/summary.json     → per-source status, record counts, elapsed time

LLM: no

Module execution order:
    1. Load run_manifest.json, extract layer_1 config
    2. For each enabled source in SCRAPERS registry: call scraper.collect(cfg)
       Sources: rss, moneycontrol, economic_times, newsdata_io, mediastack,
                gmail, youtube, india_macro, us_macro, fii_dii, bulk_deals, fno
    3. Assign sequential IDs (L1_{date}_{counter}) to every record
    4. Write raw_records.json + summary.json

Usage:
    python -m src.pipeline.L1_scraping.runner              # today
    python -m src.pipeline.L1_scraping.runner --date 2026-05-10
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, load_manifest, output_dir, today
from src.pipeline.L1_scraping.scrapers import SCRAPERS


def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l1_cfg   = manifest.get("layer_1")
    if not l1_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_1' key")

    out_dir = output_dir(date) / "L1"
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    counter = 0
    summary = {"date": date, "sources": {}}

    for source_name, scraper_fn in SCRAPERS.items():
        source_cfg = l1_cfg.get(source_name, {})
        if not source_cfg.get("enabled", True):
            print(f"  [{source_name}] disabled — skipped")
            summary["sources"][source_name] = {"status": "disabled"}
            continue

        t0 = time.time()
        try:
            raw = scraper_fn(source_cfg)
            for rec in raw:
                counter += 1
                rec["id"] = f"L1_{date.replace('-', '')}_{counter:04d}"
                records.append(rec)
            elapsed = round(time.time() - t0, 1)
            summary["sources"][source_name] = {"status": "ok", "count": len(raw), "elapsed_s": elapsed}
            print(f"  [{source_name}] {len(raw)} records ({elapsed}s)")
        except (KeyError, ValueError, RuntimeError) as e:
            # Config/programming errors — stop immediately, don't hide bugs
            raise
        except Exception as e:
            # Network/external failures — log and continue so one bad source doesn't kill the run
            summary["sources"][source_name] = {"status": "failed", "error": str(e)[:200]}
            print(f"  [{source_name}] FAILED: {e}")

    out_path = out_dir / "raw_records.json"
    out_path.write_text(json.dumps({
        "run_date":      date,
        "run_id":        manifest["run_id"],
        "total_records": len(records),
        "records":       records,
    }, indent=2, ensure_ascii=False))

    summary["total_records"] = len(records)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n  L1 done: {len(records)} records → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
