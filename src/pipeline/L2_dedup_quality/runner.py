"""
L2 Dedup + Quality Filter — removes exact duplicate records and annotates quality.

Reads:
    output/{date}/L1/raw_records.json    → flat list of scraped records (L1 output)
    output/{date}/run_manifest.json      → layer_2 config (thresholds, reliability map)

Writes:
    output/{date}/L2/filtered_records.json  → deduplicated records with quality fields appended
    output/{date}/L2/summary.json           → counts, flag breakdown, source stats

LLM: no

Module execution order:
    1. Load run_manifest.json → extract layer_2 config
    2. Load L1/raw_records.json
    3. Build source_reliability lookup from config
    4. For each record:
       a. Compute SHA-256 of content → content_hash
       b. Skip if hash already seen (exact duplicate — drop, not flag)
       c. Compute content_length
       d. Assign source_reliability (high / medium / low)
       e. Build flags list: low_content, stale
       f. Derive quality_tier from reliability + flags
    5. Write filtered_records.json + summary.json

Usage:
    python -m src.pipeline.L2_dedup_quality.runner              # today
    python -m src.pipeline.L2_dedup_quality.runner --date 2026-05-17
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config.settings import IST, load_manifest, output_dir, today


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_reliability_map(reliability_cfg: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for tier, sources in reliability_cfg.items():
        for source in sources:
            mapping[source] = tier
    return mapping


def _parse_published(published_at: str | None) -> datetime | None:
    if not published_at:
        return None
    for fmt in (None,):  # placeholder — use fromisoformat
        try:
            return datetime.fromisoformat(published_at)
        except Exception:
            return None


def _quality_tier(source_reliability: str, flags: list[str]) -> str:
    if "low_content" in flags:
        return "low"
    if source_reliability == "high" and not flags:
        return "high"
    if source_reliability == "low":
        return "low"
    return "medium"


def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l2_cfg   = manifest.get("layer_2")
    if not l2_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_2' key — re-run L0 first")

    content_length_min = int(l2_cfg.get("content_length_min", 100))
    stale_hours        = int(l2_cfg.get("stale_hours", 48))
    drop_stale         = bool(l2_cfg.get("drop_stale", True))
    reliability_map    = _build_reliability_map(l2_cfg.get("source_reliability", {}))

    l1_path = output_dir(date) / "L1" / "raw_records.json"
    if not l1_path.exists():
        raise FileNotFoundError(f"L1 output not found: {l1_path} — run L1 first")

    l1_data = json.loads(l1_path.read_text())
    raw_records: list[dict] = l1_data.get("records", [])

    stale_cutoff = datetime.now(IST) - timedelta(hours=stale_hours)

    seen_hashes: set[str] = set()
    filtered: list[dict] = []

    stats = {
        "input_count":        len(raw_records),
        "duplicates_dropped": 0,
        "stale_dropped":      0,
        "flags": {"low_content": 0, "stale": 0},
        "quality_tiers": {"high": 0, "medium": 0, "low": 0},
        "reliability": {"high": 0, "medium": 0, "low": 0},
        "by_source": {},
    }

    for rec in raw_records:
        content = rec.get("content") or ""
        h = _sha256(content)

        if h in seen_hashes:
            stats["duplicates_dropped"] += 1
            continue
        seen_hashes.add(h)

        content_length    = len(content)
        source            = rec.get("source", "")
        source_reliability = reliability_map.get(source, "medium")

        flags: list[str] = []

        if content_length < content_length_min:
            flags.append("low_content")
            stats["flags"]["low_content"] += 1

        published_dt = _parse_published(rec.get("published_at"))
        if published_dt:
            pub_aware = published_dt if published_dt.tzinfo else published_dt.replace(tzinfo=IST)
            if pub_aware < stale_cutoff:
                # market_snapshot and corporate_action records are generated at scrape
                # time and should never be dropped on staleness grounds.
                if drop_stale and rec.get("source_type") not in ("market_snapshot", "corporate_action"):
                    stats["stale_dropped"] += 1
                    continue
                flags.append("stale")
                stats["flags"]["stale"] += 1

        tier = _quality_tier(source_reliability, flags)

        rec["content_hash"]       = h
        rec["content_length"]     = content_length
        rec["source_reliability"] = source_reliability
        rec["flags"]              = flags
        rec["quality_tier"]       = tier

        filtered.append(rec)

        stats["quality_tiers"][tier]       += 1
        stats["reliability"][source_reliability] += 1
        src_stats = stats["by_source"].setdefault(source, {"count": 0, "low_content": 0, "stale": 0})
        src_stats["count"] += 1
        if "low_content" in flags:
            src_stats["low_content"] += 1
        if "stale" in flags:
            src_stats["stale"] += 1

    out_dir = output_dir(date) / "L2"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "filtered_records.json"
    out_path.write_text(json.dumps({
        "run_date":        date,
        "run_id":          l1_data.get("run_id", ""),
        "total_records":   len(filtered),
        "records":         filtered,
    }, indent=2, ensure_ascii=False))

    summary = {
        "date":               date,
        "input_count":        stats["input_count"],
        "output_count":       len(filtered),
        "duplicates_dropped": stats["duplicates_dropped"],
        "stale_dropped":      stats["stale_dropped"],
        "flags":              stats["flags"],
        "quality_tiers":      stats["quality_tiers"],
        "reliability":        stats["reliability"],
        "by_source":          stats["by_source"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"  L2 done: {stats['input_count']} in → {len(filtered)} out "
          f"({stats['duplicates_dropped']} dupes, {stats['stale_dropped']} stale dropped)")
    print(f"  Quality: high={stats['quality_tiers']['high']}, "
          f"medium={stats['quality_tiers']['medium']}, "
          f"low={stats['quality_tiers']['low']}")
    print(f"  Flags: low_content={stats['flags']['low_content']}, "
          f"stale={stats['flags']['stale']}")
    print(f"  → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
