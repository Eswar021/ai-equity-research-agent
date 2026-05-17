"""
L6 Target Selection — scores hypotheses, deduplicates, and buckets into deep_dive / watchlist / skip.

Reads:
    output/{date}/run_manifest.json          → layer_6 config
    output/{date}/L5/hypotheses.json         → 50 scored hypotheses from L5
    output/{date}/L5/market_regime.json      → current market regime (bull/bear/sideways/uncertain)

Writes:
    output/{date}/L6/selected_targets.json   → all hypotheses with bucket + score (consumed by L7)
    output/{date}/L6/summary.json            → bucket counts, score distribution

LLM: no — entirely rule-based

Module execution order:
    1. Load manifest → layer_6 config
    2. Load L5/hypotheses.json + L5/market_regime.json
    3. SCORE: composite score (0-100) per hypothesis from 4 dimensions
    4. DEDUPLICATE: normalize entity names → keep max-score per name → merge questions
    5. SORT + BUCKET: deep_dive / watchlist / skip
    6. Write selected_targets.json + summary.json

Usage:
    python -m src.pipeline.L6_target_selection.runner              # today
    python -m src.pipeline.L6_target_selection.runner --date 2026-05-17
"""

import argparse
import json
import re
from pathlib import Path

from src.config.settings import load_manifest, output_dir, today


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score(hyp: dict, regime: str, cfg: dict) -> tuple[int, dict]:
    strength_w    = cfg.get("strength_weights", {})
    sig_weight    = int(cfg.get("signal_count_weight", 2))
    sig_cap       = int(cfg.get("signal_count_cap", 30))
    div_weight    = int(cfg.get("source_diversity_weight", 5))
    div_cap       = int(cfg.get("source_diversity_cap", 20))
    regime_table  = cfg.get("regime_alignment", {})

    strength_score  = int(strength_w.get(hyp.get("strength", "weak"), 5))
    signal_score    = min(hyp.get("signal_count", 0) * sig_weight, sig_cap)
    diversity_score = min(hyp.get("source_diversity", 0) * div_weight, div_cap)

    horizon        = hyp.get("time_horizon", "medium_term")
    regime_row     = regime_table.get(regime, regime_table.get("uncertain", {}))
    regime_score   = int(regime_row.get(horizon, 5))

    total = strength_score + signal_score + diversity_score + regime_score
    breakdown = {
        "strength":        strength_score,
        "signal_volume":   signal_score,
        "source_diversity": diversity_score,
        "regime_alignment": regime_score,
    }
    return total, breakdown


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _normalize(name: str, suffixes: list[str]) -> str:
    n = name.lower().strip()
    for s in suffixes:
        if n.endswith(s):
            n = n[: -len(s)].strip()
    return n


def _deduplicate(scored: list[dict], cfg: dict) -> list[dict]:
    suffixes  = [s.lower() for s in cfg.get("dedup_strip_suffixes", [])]
    seen: dict[str, dict] = {}

    for hyp in scored:
        key = _normalize(hyp["target_entity"], suffixes)
        if key not in seen:
            seen[key] = hyp
        else:
            existing = seen[key]
            if hyp["score"] > existing["score"]:
                # keep higher-scoring one; merge questions from the lower-scoring duplicate
                merged_qs = _merge_questions(
                    existing["deep_dive_questions"],
                    hyp["deep_dive_questions"],
                )
                hyp["deep_dive_questions"] = merged_qs
                seen[key] = hyp
            else:
                # keep existing; absorb questions from this duplicate
                existing["deep_dive_questions"] = _merge_questions(
                    existing["deep_dive_questions"],
                    hyp["deep_dive_questions"],
                )

    return list(seen.values())


def _merge_questions(a: list[str], b: list[str], max_q: int = 6) -> list[str]:
    seen_q: set[str] = set()
    merged: list[str] = []
    for q in a + b:
        norm = q.strip().lower()
        if norm not in seen_q:
            seen_q.add(norm)
            merged.append(q.strip())
        if len(merged) >= max_q:
            break
    return merged


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------

def _assign_buckets(targets: list[dict], cfg: dict) -> list[dict]:
    max_dd    = int(cfg.get("max_deep_dive", 7))
    dd_min    = int(cfg.get("deep_dive_min_score", 55))
    watch_min = int(cfg.get("watchlist_min_score", 30))

    dd_count = 0
    for tgt in targets:
        if dd_count < max_dd and tgt["score"] >= dd_min:
            tgt["bucket"] = "deep_dive"
            dd_count += 1
        elif tgt["score"] >= watch_min:
            tgt["bucket"] = "watchlist"
        else:
            tgt["bucket"] = "skip"
    return targets


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l6_cfg   = manifest.get("layer_6")
    if not l6_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_6' key — re-run L0 first")

    l5_dir = output_dir(date) / "L5"
    hyp_path    = l5_dir / "hypotheses.json"
    regime_path = l5_dir / "market_regime.json"

    if not hyp_path.exists():
        raise FileNotFoundError(f"L5 hypotheses not found: {hyp_path} — run L5 first")
    if not regime_path.exists():
        raise FileNotFoundError(f"L5 market_regime not found: {regime_path} — run L5 first")

    hypotheses: list[dict] = json.loads(hyp_path.read_text()).get("hypotheses", [])
    l5_data = json.loads(hyp_path.read_text())
    regime_data = json.loads(regime_path.read_text())
    regime = regime_data.get("regime", "uncertain")

    print(f"  L6: {len(hypotheses)} hypotheses in, market_regime={regime}")

    # SCORE
    scored: list[dict] = []
    for i, hyp in enumerate(hypotheses, 1):
        if not hyp.get("parsed_ok", True):
            continue
        score, breakdown = _score(hyp, regime, l6_cfg)
        scored.append({
            "target_id":               f"TGT_{date.replace('-', '')}_{i:04d}",
            "hypothesis_id":           hyp.get("hypothesis_id", ""),
            "target_entity":           hyp.get("group_name", ""),
            "score":                   score,
            "score_breakdown":         breakdown,
            "hypothesis":              hyp.get("hypothesis", ""),
            "time_horizon":            hyp.get("time_horizon", ""),
            "strength":                hyp.get("strength", ""),
            "deep_dive_questions":     hyp.get("deep_dive_questions", []),
            "invalidating_conditions": hyp.get("invalidating_conditions", []),
            "beneficiaries":           hyp.get("beneficiaries", []),
            "group_type":              hyp.get("group_type", ""),
            "entities":                hyp.get("entities", []),
            "record_ids":              hyp.get("record_ids", []),
            "weight_score":            hyp.get("weight_score", 0),
            "signal_count":            hyp.get("signal_count", 0),
            "source_diversity":        hyp.get("source_diversity", 0),
        })

    # DEDUPLICATE
    before_dedup = len(scored)
    scored = _deduplicate(scored, l6_cfg)
    after_dedup  = len(scored)
    dupes_removed = before_dedup - after_dedup
    if dupes_removed:
        print(f"  Dedup: removed {dupes_removed} near-duplicate targets")

    # SORT + BUCKET
    scored.sort(key=lambda t: t["score"], reverse=True)
    scored = _assign_buckets(scored, l6_cfg)

    bucket_counts: dict[str, int] = {"deep_dive": 0, "watchlist": 0, "skip": 0}
    for t in scored:
        bucket_counts[t["bucket"]] = bucket_counts.get(t["bucket"], 0) + 1

    print(f"  Buckets: deep_dive={bucket_counts['deep_dive']}, "
          f"watchlist={bucket_counts['watchlist']}, skip={bucket_counts['skip']}")
    print("  Deep-dive targets:")
    for tgt in [t for t in scored if t["bucket"] == "deep_dive"]:
        print(f"    [{tgt['score']:3d}] {tgt['target_entity']:35s} "
              f"{tgt['strength']:6s} {tgt['time_horizon']}")

    out_dir = output_dir(date) / "L6"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "selected_targets.json"
    out_path.write_text(json.dumps({
        "run_date":              date,
        "run_id":                l5_data.get("run_id", ""),
        "market_regime":         regime,
        "total_hypotheses_in":   before_dedup,
        "total_after_dedup":     after_dedup,
        "buckets":               bucket_counts,
        "targets":               scored,
    }, indent=2, ensure_ascii=False))

    scores = [t["score"] for t in scored]
    (out_dir / "summary.json").write_text(json.dumps({
        "date":                  date,
        "market_regime":         regime,
        "total_hypotheses_in":   before_dedup,
        "total_after_dedup":     after_dedup,
        "dupes_removed":         dupes_removed,
        "buckets":               bucket_counts,
        "score_min":             min(scores) if scores else 0,
        "score_max":             max(scores) if scores else 0,
        "score_mean":            round(sum(scores) / len(scores), 1) if scores else 0,
    }, indent=2))

    print(f"\n  L6 done: {after_dedup} targets → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
