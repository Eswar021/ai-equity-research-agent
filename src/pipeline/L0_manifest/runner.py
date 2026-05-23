"""
L0 Manifest — resolves config files into a single run_manifest.json for the run.

Reads:
    src/config/l1_sources.yaml   → layer_1 source config
    src/config/l2_filters.yaml   → layer_2 dedup + quality filter thresholds
    src/config/l3_config.yaml    → layer_3 LLM extraction settings
    src/config/l4_config.yaml    → layer_4 memory qualification thresholds
    src/config/l5_config.yaml    → layer_5 hypothesis generation settings
    src/config/l6_config.yaml    → layer_6 target selection thresholds
    src/config/l7_config.yaml    → layer_7 deep-dive collection settings
    src/config/l8_config.yaml    → layer_8 evidence builder settings
    src/config/l9_config.yaml    → layer_9 specialist analysis agent settings
    src/config/l10_config.yaml   → layer_10 final report + composite scoring settings

Writes:
    output/{date}/run_manifest.json  → config snapshot consumed by all downstream layers

LLM: no

Module execution order:
    1.  Load l1_sources.yaml  → layer_1 config
    2.  Load l2_filters.yaml  → layer_2 config
    3.  Load l3_config.yaml   → layer_3 config
    4.  Load l4_config.yaml   → layer_4 config
    5.  Load l5_config.yaml   → layer_5 config
    6.  Load l6_config.yaml   → layer_6 config
    7.  Load l7_config.yaml   → layer_7 config
    8.  Load l8_config.yaml   → layer_8 config
    9.  Load l9_config.yaml   → layer_9 config
   10.  Load l10_config.yaml  → layer_10 config
   11. Build manifest dict with run_date, run_id, created_at, layer_1..10 keys
   12. Write run_manifest.json

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
_L2_FILTERS_YAML = PROJECT_ROOT / "src" / "config" / "l2_filters.yaml"
_L3_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l3_config.yaml"
_L4_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l4_config.yaml"
_L5_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l5_config.yaml"
_L6_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l6_config.yaml"
_L7_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l7_config.yaml"
_L8_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l8_config.yaml"
_L9_CONFIG_YAML  = PROJECT_ROOT / "src" / "config" / "l9_config.yaml"
_L10_CONFIG_YAML = PROJECT_ROOT / "src" / "config" / "l10_config.yaml"


def _load_l1_config() -> dict:
    if not _L1_SOURCES_YAML.exists():
        raise FileNotFoundError(f"L1 sources config not found: {_L1_SOURCES_YAML}")
    raw = yaml.safe_load(_L1_SOURCES_YAML.read_text())
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ValueError(f"l1_sources.yaml must have a top-level 'sources' dict, got: {type(sources)}")
    return {**sources, "max_workers": raw.get("max_workers", 8)}


def _load_l2_config() -> dict:
    if not _L2_FILTERS_YAML.exists():
        raise FileNotFoundError(f"L2 filters config not found: {_L2_FILTERS_YAML}")
    raw = yaml.safe_load(_L2_FILTERS_YAML.read_text())
    cfg = raw.get("layer_2")
    if not isinstance(cfg, dict):
        raise ValueError(f"l2_filters.yaml must have a top-level 'layer_2' dict, got: {type(cfg)}")
    return cfg


def _load_l3_config() -> dict:
    if not _L3_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L3 config not found: {_L3_CONFIG_YAML}")
    raw = yaml.safe_load(_L3_CONFIG_YAML.read_text())
    cfg = raw.get("layer_3")
    if not isinstance(cfg, dict):
        raise ValueError(f"l3_config.yaml must have a top-level 'layer_3' dict, got: {type(cfg)}")
    return cfg


def _load_l4_config() -> dict:
    if not _L4_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L4 config not found: {_L4_CONFIG_YAML}")
    raw = yaml.safe_load(_L4_CONFIG_YAML.read_text())
    cfg = raw.get("layer_4")
    if not isinstance(cfg, dict):
        raise ValueError(f"l4_config.yaml must have a top-level 'layer_4' dict, got: {type(cfg)}")
    return cfg


def _load_l5_config() -> dict:
    if not _L5_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L5 config not found: {_L5_CONFIG_YAML}")
    raw = yaml.safe_load(_L5_CONFIG_YAML.read_text())
    cfg = raw.get("layer_5")
    if not isinstance(cfg, dict):
        raise ValueError(f"l5_config.yaml must have a top-level 'layer_5' dict, got: {type(cfg)}")
    return cfg


def _load_l6_config() -> dict:
    if not _L6_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L6 config not found: {_L6_CONFIG_YAML}")
    raw = yaml.safe_load(_L6_CONFIG_YAML.read_text())
    cfg = raw.get("layer_6")
    if not isinstance(cfg, dict):
        raise ValueError(f"l6_config.yaml must have a top-level 'layer_6' dict, got: {type(cfg)}")
    return cfg


def _load_l7_config() -> dict:
    if not _L7_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L7 config not found: {_L7_CONFIG_YAML}")
    raw = yaml.safe_load(_L7_CONFIG_YAML.read_text())
    cfg = raw.get("layer_7")
    if not isinstance(cfg, dict):
        raise ValueError(f"l7_config.yaml must have a top-level 'layer_7' dict, got: {type(cfg)}")
    return cfg


def _load_l8_config() -> dict:
    if not _L8_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L8 config not found: {_L8_CONFIG_YAML}")
    raw = yaml.safe_load(_L8_CONFIG_YAML.read_text())
    cfg = raw.get("layer_8")
    if not isinstance(cfg, dict):
        raise ValueError(f"l8_config.yaml must have a top-level 'layer_8' dict, got: {type(cfg)}")
    return cfg


def _load_l9_config() -> dict:
    if not _L9_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L9 config not found: {_L9_CONFIG_YAML}")
    raw = yaml.safe_load(_L9_CONFIG_YAML.read_text())
    cfg = raw.get("layer_9")
    if not isinstance(cfg, dict):
        raise ValueError(f"l9_config.yaml must have a top-level 'layer_9' dict, got: {type(cfg)}")
    return cfg


def _load_l10_config() -> dict:
    if not _L10_CONFIG_YAML.exists():
        raise FileNotFoundError(f"L10 config not found: {_L10_CONFIG_YAML}")
    raw = yaml.safe_load(_L10_CONFIG_YAML.read_text())
    cfg = raw.get("layer_10")
    if not isinstance(cfg, dict):
        raise ValueError(f"l10_config.yaml must have a top-level 'layer_10' dict, got: {type(cfg)}")
    return cfg


def run(run_date: str | None = None) -> Path:
    date    = run_date or today()
    out_dir = output_dir(date)
    out_dir.mkdir(parents=True, exist_ok=True)

    l1_cfg = _load_l1_config()
    l2_cfg = _load_l2_config()
    l3_cfg = _load_l3_config()
    l4_cfg = _load_l4_config()
    l5_cfg = _load_l5_config()
    l6_cfg = _load_l6_config()
    l7_cfg = _load_l7_config()
    l8_cfg = _load_l8_config()
    l9_cfg  = _load_l9_config()
    l10_cfg = _load_l10_config()

    manifest = {
        "run_date":   date,
        "run_id":     f"RUN_{date.replace('-', '')}_{datetime.now(IST).strftime('%H%M')}",
        "created_at": datetime.now(IST).isoformat(),
        "layer_1":    l1_cfg,
        "layer_2":    l2_cfg,
        "layer_3":    l3_cfg,
        "layer_4":    l4_cfg,
        "layer_5":    l5_cfg,
        "layer_6":    l6_cfg,
        "layer_7":    l7_cfg,
        "layer_8":    l8_cfg,
        "layer_9":    l9_cfg,
        "layer_10":   l10_cfg,
    }

    out_path = out_dir / "run_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(f"  L0 done: run_manifest written → {out_path}")
    print(f"  Layer 1 sources: {', '.join(k for k, v in l1_cfg.items() if isinstance(v, dict) and v.get('enabled', True))}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
