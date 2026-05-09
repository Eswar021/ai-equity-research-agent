"""
layer1_bundler.py — Layer 1 contract producer

Runs as the final step of Phase A (run_phase_a.py).
Scans all Phase A output subdirectories and assembles 4 contract files
in output/{date}/layer1/ that Layer 2 (canonicalization) reads:

  raw_context_bundle.json    — all collector outputs, one item per file
  raw_source_records.json    — per-module status + file counts
  collection_status.json     — aggregate run health
  data_freshness_report.json — freshness classification per module

Standalone:
  python context_ext_layer/layer1_bundler.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config.paths import PHASE_A_DIR, LAYER1_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

# Maps PHASE_A_DIR subdirectory name → (source_type, freshness_type)
_MODULE_META: dict[str, tuple[str, str]] = {
    "moneycontrol":    ("news_article",       "historical_available"),
    "economic_times":  ("news_article",       "historical_available"),
    "rss":             ("rss_item",           "historical_available"),
    "newsdata_io":     ("news_api",           "historical_available"),
    "mediastack":      ("news_api",           "historical_available"),
    "gmail":           ("newsletter",         "historical_available"),
    "youtube":         ("youtube_transcript", "historical_available"),
    "macro_data":      ("macro_snapshot",     "historical_available"),
    "fii_dii":         ("institutional_flow", "today_only"),
    "bulk_deals":      ("bulk_block_deals",   "today_only"),
    "fno_data":        ("derivatives_snapshot", "live_snapshot"),
    "browser_scraped": ("generic_web",        "historical_available"),
    "generic_web":     ("generic_web",        "historical_available"),
}


def _count_records(content) -> int:
    """Best-effort count of logical records inside a loaded JSON value."""
    if isinstance(content, list):
        return len(content)
    if isinstance(content, dict):
        for key in ("articles", "items", "results", "data", "signals", "records"):
            if isinstance(content.get(key), list):
                return len(content[key])
        return 1
    return 1


def bundle(phase_a_dir: Path = PHASE_A_DIR, layer1_dir: Path = LAYER1_DIR) -> dict:
    """Assemble Layer 1 contract files from all Phase A outputs."""
    now = datetime.now(_IST)
    layer1_dir.mkdir(parents=True, exist_ok=True)

    bundle_items: list[dict] = []
    source_records: list[dict] = []

    # Walk every known subdirectory in Phase A output
    all_subdirs = sorted(phase_a_dir.iterdir()) if phase_a_dir.exists() else []

    for subdir in all_subdirs:
        if not subdir.is_dir():
            continue
        module_name = subdir.name
        source_type, freshness_type = _MODULE_META.get(
            module_name, ("unknown", "historical_available")
        )

        json_files = sorted(subdir.glob("*.json"))
        if not json_files:
            source_records.append({
                "source_module":  module_name,
                "source_type":    source_type,
                "freshness_type": freshness_type,
                "status":         "empty",
                "file_count":     0,
                "record_count":   0,
                "files":          [],
            })
            continue

        module_records = 0
        module_files: list[str] = []

        for jf in json_files:
            try:
                content = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:
                continue

            record_count = _count_records(content)
            module_records += record_count
            module_files.append(jf.name)

            bundle_items.append({
                "source_module":  module_name,
                "source_type":    source_type,
                "freshness_type": freshness_type,
                "source_file":    str(jf),
                "record_count":   record_count,
                "content":        content,
            })

        source_records.append({
            "source_module":  module_name,
            "source_type":    source_type,
            "freshness_type": freshness_type,
            "status":         "ok" if module_files else "empty",
            "file_count":     len(module_files),
            "record_count":   module_records,
            "files":          module_files,
        })

    # ── raw_context_bundle.json ───────────────────────────────────────────────
    bundle_file = layer1_dir / "raw_context_bundle.json"
    bundle_file.write_text(json.dumps({
        "bundle_version": "1.0",
        "generated_at":   now.isoformat(),
        "phase_a_dir":    str(phase_a_dir),
        "total_items":    len(bundle_items),
        "items":          bundle_items,
    }, ensure_ascii=False, indent=2))

    # ── raw_source_records.json ───────────────────────────────────────────────
    src_file = layer1_dir / "raw_source_records.json"
    src_file.write_text(json.dumps(source_records, ensure_ascii=False, indent=2))

    # ── collection_status.json ────────────────────────────────────────────────
    ok      = sum(1 for r in source_records if r["status"] == "ok")
    empty   = sum(1 for r in source_records if r["status"] == "empty")
    status  = {
        "generated_at":     now.isoformat(),
        "modules_total":    len(source_records),
        "modules_ok":       ok,
        "modules_empty":    empty,
        "total_files":      sum(r["file_count"] for r in source_records),
        "total_records":    sum(r["record_count"] for r in source_records),
        "by_module":        {r["source_module"]: r["status"] for r in source_records},
    }
    status_file = layer1_dir / "collection_status.json"
    status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2))

    # ── data_freshness_report.json ────────────────────────────────────────────
    freshness_groups: dict[str, list[str]] = {}
    for r in source_records:
        ft = r["freshness_type"]
        freshness_groups.setdefault(ft, []).append(r["source_module"])

    freshness_report = {
        "generated_at": now.isoformat(),
        "summary":      freshness_groups,
        "by_module":    {r["source_module"]: r["freshness_type"] for r in source_records},
    }
    freshness_file = layer1_dir / "data_freshness_report.json"
    freshness_file.write_text(json.dumps(freshness_report, ensure_ascii=False, indent=2))

    return {
        "bundle_file":    str(bundle_file),
        "src_file":       str(src_file),
        "status_file":    str(status_file),
        "freshness_file": str(freshness_file),
        "total_items":    len(bundle_items),
        "modules_ok":     ok,
        "modules_empty":  empty,
    }


if __name__ == "__main__":
    result = bundle()
    print(f"Layer 1 bundle → {Path(result['bundle_file']).parent}")
    print(f"  Items bundled : {result['total_items']}")
    print(f"  Modules ok    : {result['modules_ok']}")
    print(f"  Modules empty : {result['modules_empty']}")
