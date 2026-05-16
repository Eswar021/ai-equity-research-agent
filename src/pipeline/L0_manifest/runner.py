"""
L0 Manifest — resolves config files into a single run_manifest.json for the run.

Reads:
    src/config/l1_sources.yaml   → layer_1 source config

Writes:
    output/{date}/run_manifest.json  → config snapshot consumed by all downstream layers

LLM: no

Module execution order:
    1. Load l1_sources.yaml
    2. Build manifest dict with run_date, run_id, created_at, layer_1 keys
    3. Write run_manifest.json

Usage:
    python -m src.pipeline.L0_manifest.runner              # today
    python -m src.pipeline.L0_manifest.runner --date 2026-05-17
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import yaml

from src.config.settings import IST, PROJECT_ROOT, output_dir, today

_L1_SOURCES_YAML = PROJECT_ROOT / "src" / "config" / "l1_sources.yaml"


def _load_l1_config() -> dict:
    if not _L1_SOURCES_YAML.exists():
        raise FileNotFoundError(f"L1 sources config not found: {_L1_SOURCES_YAML}")
    raw = yaml.safe_load(_L1_SOURCES_YAML.read_text())
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ValueError(f"l1_sources.yaml must have a top-level 'sources' dict, got: {type(sources)}")
    return sources


def run(run_date: str | None = None) -> Path:
    date    = run_date or today()
    out_dir = output_dir(date)
    out_dir.mkdir(parents=True, exist_ok=True)

    l1_cfg = _load_l1_config()

    manifest = {
        "run_date":   date,
        "run_id":     f"RUN_{date.replace('-', '')}_{datetime.now(IST).strftime('%H%M')}",
        "created_at": datetime.now(IST).isoformat(),
        "layer_1":    l1_cfg,
    }

    out_path = out_dir / "run_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"  L0 done: run_manifest written → {out_path}")
    print(f"  Layer 1 sources: {', '.join(k for k, v in l1_cfg.items() if v.get('enabled', True))}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
