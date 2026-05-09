"""
layer7_bundler.py — Layer 7 contract producer

Runs as the final step of Phase C (run_phase_c.py).
Takes the per-ticker module results dict from Phase C and assembles 4 contract
files in output/{date}/layer7/ that Layer 2 (second-pass canonicalization) reads:

  raw_deep_dive_bundle.json  — all per-ticker module outputs, one item per file
  raw_source_records.json    — per-module status + ticker counts
  collection_status.json     — aggregate run health
  data_freshness_report.json — freshness classification per module

Standalone:
  python context_ext_layer/layer7_bundler.py
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config.paths import PHASE_C_DIR, LAYER7_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

# Maps Phase C module names → (source_type, freshness_type)
_MODULE_META: dict[str, tuple[str, str]] = {
    "market_data":       ("market_snapshot",   "historical_available"),
    "price_history":     ("price_history",      "historical_available"),
    "screener_in":       ("fundamental_data",   "historical_available"),
    "peer_comparison":   ("peer_data",          "historical_available"),
    "analyst_estimates": ("analyst_consensus",  "historical_available"),
    "exchange_filings":  ("regulatory_filing",  "historical_available"),
    "filing_docs":       ("filing_document",    "historical_available"),
    "corporate_actions": ("corporate_action",   "historical_available"),
    "sec_filings":       ("regulatory_filing",  "historical_available"),
    "fno_data":          ("derivatives_snapshot", "live_snapshot"),
}


def _count_records(content) -> int:
    if isinstance(content, list):
        return len(content)
    if isinstance(content, dict):
        for key in ("articles", "items", "results", "data", "records", "announcements"):
            if isinstance(content.get(key), list):
                return len(content[key])
        return 1
    return 1


def bundle(
    ticker_results: dict[str, dict] | None = None,
    phase_c_dir: Path = PHASE_C_DIR,
    layer7_dir: Path = LAYER7_DIR,
) -> dict:
    """
    Assemble Layer 7 contract files from Phase C outputs.

    ticker_results: dict produced by run_phase_c.run(), mapping
        ticker → {module_name: file_path_or_None}.
        If None, reconstructs by scanning phase_c_dir subdirectories.
    """
    now = datetime.now(_IST)
    layer7_dir.mkdir(parents=True, exist_ok=True)

    # If ticker_results not provided, reconstruct by scanning the phaseC dir
    if ticker_results is None:
        ticker_results = _scan_phase_c_dir(phase_c_dir)

    bundle_items: list[dict] = []
    # module_name → {ok: int, missing: int, files: list}
    module_stats: dict[str, dict] = {}

    for ticker, module_files in ticker_results.items():
        ticker_entry: dict[str, dict] = {}

        for module_name, file_path in module_files.items():
            source_type, freshness_type = _MODULE_META.get(
                module_name, ("unknown", "historical_available")
            )
            stats = module_stats.setdefault(module_name, {
                "source_type": source_type,
                "freshness_type": freshness_type,
                "tickers_ok": 0,
                "tickers_missing": 0,
                "files": [],
            })

            if file_path and Path(file_path).exists():
                try:
                    content = json.loads(Path(file_path).read_text(encoding="utf-8"))
                    ticker_entry[module_name] = {
                        "source_file":   str(file_path),
                        "record_count":  _count_records(content),
                        "content":       content,
                    }
                    stats["tickers_ok"] += 1
                    stats["files"].append(Path(file_path).name)
                except Exception:
                    ticker_entry[module_name] = None
                    stats["tickers_missing"] += 1
            else:
                ticker_entry[module_name] = None
                stats["tickers_missing"] += 1

        bundle_items.append({
            "ticker":      ticker,
            "modules":     ticker_entry,
        })

    # ── raw_deep_dive_bundle.json ─────────────────────────────────────────────
    bundle_file = layer7_dir / "raw_deep_dive_bundle.json"
    bundle_file.write_text(json.dumps({
        "bundle_version": "1.0",
        "generated_at":   now.isoformat(),
        "phase_c_dir":    str(phase_c_dir),
        "total_tickers":  len(bundle_items),
        "items":          bundle_items,
    }, ensure_ascii=False, indent=2))

    # ── raw_source_records.json ───────────────────────────────────────────────
    source_records = [
        {
            "source_module":  mod,
            "source_type":    s["source_type"],
            "freshness_type": s["freshness_type"],
            "status":         "ok" if s["tickers_ok"] > 0 else "empty",
            "tickers_ok":     s["tickers_ok"],
            "tickers_missing": s["tickers_missing"],
            "file_count":     len(s["files"]),
            "files":          s["files"],
        }
        for mod, s in module_stats.items()
    ]
    src_file = layer7_dir / "raw_source_records.json"
    src_file.write_text(json.dumps(source_records, ensure_ascii=False, indent=2))

    # ── collection_status.json ────────────────────────────────────────────────
    ok_modules = sum(1 for r in source_records if r["status"] == "ok")
    status = {
        "generated_at":     now.isoformat(),
        "tickers_processed": len(bundle_items),
        "modules_total":    len(source_records),
        "modules_ok":       ok_modules,
        "modules_empty":    len(source_records) - ok_modules,
        "by_module":        {r["source_module"]: r["status"] for r in source_records},
    }
    status_file = layer7_dir / "collection_status.json"
    status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2))

    # ── data_freshness_report.json ────────────────────────────────────────────
    freshness_groups: dict[str, list[str]] = {}
    for r in source_records:
        freshness_groups.setdefault(r["freshness_type"], []).append(r["source_module"])

    freshness_report = {
        "generated_at": now.isoformat(),
        "summary":      freshness_groups,
        "by_module":    {r["source_module"]: r["freshness_type"] for r in source_records},
    }
    freshness_file = layer7_dir / "data_freshness_report.json"
    freshness_file.write_text(json.dumps(freshness_report, ensure_ascii=False, indent=2))

    return {
        "bundle_file":       str(bundle_file),
        "src_file":          str(src_file),
        "status_file":       str(status_file),
        "freshness_file":    str(freshness_file),
        "total_tickers":     len(bundle_items),
        "modules_ok":        ok_modules,
    }


def _scan_phase_c_dir(phase_c_dir: Path) -> dict[str, dict]:
    """Reconstruct ticker_results by scanning phaseC subdirectories."""
    if not phase_c_dir.exists():
        return {}

    # Find all tickers by looking at files named {TICKER}_{module}.json or similar
    ticker_results: dict[str, dict] = {}

    for module_dir in sorted(phase_c_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        module_name = module_dir.name

        for jf in sorted(module_dir.glob("*.json")):
            # Filenames follow pattern: TICKER_NS_modulename_YYYYMMDD.json or similar
            # Extract ticker from filename: everything before the first known module suffix
            stem = jf.stem
            ticker = _extract_ticker_from_stem(stem, module_name)
            if ticker:
                ticker_results.setdefault(ticker, {})[module_name] = str(jf)

    return ticker_results


def _extract_ticker_from_stem(stem: str, module_name: str) -> str | None:
    """Best-effort ticker extraction from a Phase C filename stem."""
    # Filenames are typically: BHEL_NS_market_data or BHEL_NS_history_1y etc.
    # Tickers have format like BHEL_NS (replacing . with _)
    # Strategy: strip known module-name suffixes and date suffixes
    parts = stem.split("_")
    # Most tickers are 1-2 parts (e.g. BHEL_NS, HDFCBANK_NS)
    # Try: first 2 parts as ticker
    if len(parts) >= 2:
        ticker_raw = "_".join(parts[:2])
        # Re-add the .NS or .BO suffix
        if parts[1].upper() in ("NS", "BO"):
            return ticker_raw.replace("_NS", ".NS").replace("_BO", ".BO")
    return None


if __name__ == "__main__":
    result = bundle()
    print(f"Layer 7 bundle → {Path(result['bundle_file']).parent}")
    print(f"  Tickers bundled : {result['total_tickers']}")
    print(f"  Modules ok      : {result['modules_ok']}")
