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
    2. Run all enabled scrapers in parallel (ThreadPoolExecutor, max_workers from config)
       Sources: rss, moneycontrol, economic_times, newsdata_io, mediastack,
                gmail, youtube, india_macro, us_macro, fii_dii, bulk_deals, fno
    3. Assign sequential IDs (L1_{date}_{counter}) in stable SCRAPERS order
    4. Write raw_records.json + summary.json

Usage:
    python -m src.pipeline.L1_scraping.runner              # today
    python -m src.pipeline.L1_scraping.runner --date 2026-05-10
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from src.config.settings import load_manifest, output_dir, today
from src.pipeline.L1_scraping.scrapers import SCRAPERS


def _run_scraper(
    source_name: str,
    scraper_fn,
    source_cfg: dict,
) -> tuple[str, list[dict], float, str | None]:
    """
    Run one scraper. Returns (source_name, records, elapsed_s, error).
    Config/programming errors (KeyError, ValueError, RuntimeError) re-raise to
    propagate through the future and stop the run. Network/external errors are
    caught and returned as an error string so one bad source doesn't kill the run.
    """
    t0 = time.time()
    try:
        records = scraper_fn(source_cfg)
        return source_name, records, round(time.time() - t0, 1), None
    except (KeyError, ValueError, RuntimeError):
        raise
    except Exception as e:
        return source_name, [], round(time.time() - t0, 1), str(e)[:200]


def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l1_cfg   = manifest.get("layer_1")
    if not l1_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_1' key")

    max_workers = int(l1_cfg.get("max_workers", 8))
    out_dir = output_dir(date) / "L1"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict = {"date": date, "sources": {}}

    # Submit all enabled scrapers in parallel
    results: dict[str, tuple[list[dict], float, str | None]] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_name: dict = {}
        for source_name, scraper_fn in SCRAPERS.items():
            source_cfg = l1_cfg.get(source_name, {})
            if not source_cfg.get("enabled", True):
                print(f"  [{source_name}] disabled — skipped")
                summary["sources"][source_name] = {"status": "disabled"}
                continue
            future_to_name[pool.submit(_run_scraper, source_name, scraper_fn, source_cfg)] = source_name

        for future in as_completed(future_to_name):
            sname = future_to_name[future]
            # re-raises KeyError/ValueError/RuntimeError (programming errors) so the run stops
            _, raw, elapsed, error = future.result()
            results[sname] = (raw, elapsed, error)
            if error:
                print(f"  [{sname}] FAILED: {error}")
            else:
                print(f"  [{sname}] {len(raw)} records ({elapsed}s)")

    # Assign IDs in stable SCRAPERS order so IDs are deterministic regardless of completion order
    records: list[dict] = []
    counter = 0

    for source_name in SCRAPERS:
        source_cfg = l1_cfg.get(source_name, {})
        if not source_cfg.get("enabled", True):
            continue
        if source_name not in results:
            continue

        raw, elapsed, error = results[source_name]
        if error:
            summary["sources"][source_name] = {"status": "failed", "error": error}
        else:
            for rec in raw:
                counter += 1
                rec["id"] = f"L1_{date.replace('-', '')}_{counter:04d}"
                records.append(rec)
            summary["sources"][source_name] = {
                "status":    "ok",
                "count":     len(raw),
                "elapsed_s": elapsed,
            }

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
