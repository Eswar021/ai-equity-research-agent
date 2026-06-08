"""
L8 Evidence Builder — assembles self-contained evidence packets for L9 specialist agents.

Joins four upstream outputs into one evidence_packets.json — one packet per deep-dive target.
Each packet has everything an L9 agent needs: thesis, market data, supporting news, and
evidence gaps. No lookbacks, no ID chains.

Reads:
    output/{date}/run_manifest.json              → layer_8 config
    output/{date}/L4/memory_context.json         → enriched records + recalled past memories
    output/{date}/L5/hypotheses.json             → full hypothesis text per hypothesis_id
    output/{date}/L6/selected_targets.json       → deep_dive targets with scores + record_ids
    output/{date}/L7/target_evidence_bundles.json → ticker market data per target

Writes:
    output/{date}/L8/evidence_packets.json       → one packet per target (consumed by L9)
    output/{date}/L8/summary.json                → record counts, gap stats, elapsed time

LLM: no

Module execution order:
    1. Load manifest → layer_8 config
    2. Load L4/memory_context.json → record_index + recalled past context
    3. Load L5/hypotheses.json → hypothesis_index {hypothesis_id: hypothesis}
    4. Load L6/selected_targets.json → deep_dive targets
    5. Load L7/target_evidence_bundles.json → bundle_index {target_id: bundle}
    6. For each target:
       a. Look up L5 hypothesis → thesis context
       b. Look up L7 bundle → market data + resolution info
       c. news_matcher.match() → supporting_news
       d. gap_detector.detect() → evidence_gaps
       e. Assemble packet
    7. Write L8/evidence_packets.json
    8. Write L8/summary.json

Usage:
    python -m src.pipeline.L8_evidence_builder.runner              # today
    python -m src.pipeline.L8_evidence_builder.runner --date 2026-05-17
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.config.settings import load_manifest, output_dir, today

from . import gap_detector as gd
from . import news_matcher as nm


def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l8_cfg   = manifest.get("layer_8")
    if not l8_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_8' key — re-run L0 first")

    out_dir = output_dir(date) / "L8"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load L4 — enriched records + recalled past memories
    l4_path = output_dir(date) / "L4" / "memory_context.json"
    if not l4_path.exists():
        raise FileNotFoundError(f"L4 output not found: {l4_path} — run L4 first")

    l4_data      = json.loads(l4_path.read_text())
    all_records  = l4_data.get("records", [])
    record_index = {r["id"]: r for r in all_records if r.get("id")}
    past_memories = l4_data.get("memory", [])
    print(f"  L8: {len(all_records)} L4 records loaded, {len(past_memories)} recalled memories")

    # Load L5 — hypothesis text indexed by hypothesis_id
    l5_path = output_dir(date) / "L5" / "hypotheses.json"
    if not l5_path.exists():
        raise FileNotFoundError(f"L5 output not found: {l5_path} — run L5 first")

    l5_data        = json.loads(l5_path.read_text())
    hyp_index: dict = {h["hypothesis_id"]: h for h in l5_data.get("hypotheses", [])}

    # Load L6 — deep_dive targets only
    l6_path = output_dir(date) / "L6" / "selected_targets.json"
    if not l6_path.exists():
        raise FileNotFoundError(f"L6 output not found: {l6_path} — run L6 first")

    l6_data = json.loads(l6_path.read_text())
    targets = [t for t in l6_data.get("targets", []) if t.get("bucket") == "deep_dive"]
    print(f"  L8: {len(targets)} deep-dive targets")

    # Load L7 — bundle dict indexed by target_id
    l7_path = output_dir(date) / "L7" / "target_evidence_bundles.json"
    if not l7_path.exists():
        raise FileNotFoundError(f"L7 output not found: {l7_path} — run L7 first")

    l7_data       = json.loads(l7_path.read_text())
    bundle_index  = {b["target_id"]: b for b in l7_data.get("bundles", [])}
    market_regime = l7_data.get("market_regime", "uncertain")

    # Build evidence packets
    run_start = time.time()
    packets: list[dict] = []
    stats = {"total_news_matched": 0, "hypothesis_source": 0, "entity_match": 0, "total_gaps": 0}

    for target in targets:
        target_id  = target.get("target_id", "")
        bundle     = bundle_index.get(target_id, {})

        # For promoted watchlist targets, thesis metadata comes from the bundle (watchlist
        # candidate), not from the original L6 deep_dive target — they are different entities.
        thesis_src = bundle if bundle.get("promoted_from_watchlist") else target
        hyp_id     = thesis_src.get("hypothesis_id", "") or target.get("hypothesis_id", "")
        hypothesis = hyp_index.get(hyp_id, {})

        # Supporting news: 2-pass match
        supporting_news = nm.match(thesis_src, bundle, record_index, all_records, l8_cfg)

        # Past context: recalled memories for entities in this target (grows with pipeline history)
        past_context = [
            m for m in past_memories
            if _memory_relevant(m, thesis_src, bundle)
        ]

        # Evidence gaps
        evidence_gaps = gd.detect(bundle, thesis_src, supporting_news, l8_cfg)

        # Packet quality metrics
        hyp_src = sum(1 for r in supporting_news if r["relevance_type"] == "hypothesis_source")
        ent_src = sum(1 for r in supporting_news if r["relevance_type"] == "entity_match")
        ticker_statuses = [
            v.get("collection_status", "unknown")
            for v in bundle.get("ticker_data", {}).values()
        ]
        ready = len(bundle.get("ticker_data", {})) > 0 and len(supporting_news) > 0

        packets.append({
            "target_id":     target_id,
            "target_entity": bundle.get("target_entity") or target.get("target_entity", ""),
            "bucket":        target.get("bucket", ""),
            "score":         target.get("score", 0),
            "score_breakdown": target.get("score_breakdown", {}),
            "time_horizon":  thesis_src.get("time_horizon") or target.get("time_horizon", ""),
            "strength":      thesis_src.get("strength") or target.get("strength", ""),

            "thesis": {
                "hypothesis":           hypothesis.get("hypothesis") or thesis_src.get("hypothesis", ""),
                "beneficiaries":        thesis_src.get("beneficiaries", []),
                "deep_dive_questions":  thesis_src.get("deep_dive_questions", []),
                "invalidating_conditions": thesis_src.get("invalidating_conditions", []),
            },

            "resolution": {
                "type":    bundle.get("resolution_type", "unresolved"),
                "tickers": bundle.get("resolved_tickers", []),
                "note":    bundle.get("resolution_note", ""),
            },

            "macro_context": bundle.get("macro_context", {}),

            "market_data": bundle.get("ticker_data", {}),

            "supporting_news": supporting_news,

            "past_context": past_context,

            "evidence_gaps": evidence_gaps,

            "packet_quality": {
                "news_records_matched":    len(supporting_news),
                "hypothesis_source_records": hyp_src,
                "entity_match_records":    ent_src,
                "tickers_complete":  ticker_statuses.count("complete"),
                "tickers_partial":   ticker_statuses.count("partial"),
                "tickers_failed":    ticker_statuses.count("failed"),
                "evidence_gaps_count": len(evidence_gaps),
                "ready_for_agents":  ready,
            },
        })

        stats["total_news_matched"] += len(supporting_news)
        stats["hypothesis_source"]  += hyp_src
        stats["entity_match"]       += ent_src
        stats["total_gaps"]         += len(evidence_gaps)

        print(f"  [{target.get('target_entity', ''):35s}]  "
              f"news={len(supporting_news):3d}  gaps={len(evidence_gaps):2d}  "
              f"ready={ready}")

    out_path = out_dir / "evidence_packets.json"
    out_path.write_text(json.dumps({
        "run_date":      date,
        "run_id":        l6_data.get("run_id", ""),
        "market_regime": market_regime,
        "total_targets": len(packets),
        "packets":       packets,
    }, indent=2, ensure_ascii=False))

    elapsed = round(time.time() - run_start, 1)
    ready_count = sum(1 for p in packets if p["packet_quality"]["ready_for_agents"])

    (out_dir / "summary.json").write_text(json.dumps({
        "date":                  date,
        "market_regime":         market_regime,
        "total_targets":         len(packets),
        "ready_for_agents":      ready_count,
        "total_news_matched":    stats["total_news_matched"],
        "hypothesis_source":     stats["hypothesis_source"],
        "entity_match":          stats["entity_match"],
        "total_evidence_gaps":   stats["total_gaps"],
        "l4_records_available":  len(all_records),
        "recalled_memories":     len(past_memories),
        "elapsed_s":             elapsed,
    }, indent=2))

    print(f"\n  L8 done in {elapsed}s: {len(packets)} packets, "
          f"{ready_count} ready for agents, {stats['total_gaps']} total gaps")
    print(f"  → {out_path}")
    return out_path


def _memory_relevant(memory: dict, target: dict, bundle: dict) -> bool:
    """True if a recalled memory record mentions this target's entities or tickers."""
    entity = target.get("target_entity", "").lower()
    tickers = {t.lower() for t in bundle.get("resolved_tickers", [])}
    candidates = {entity} | tickers | {
        b.lower() for b in target.get("beneficiaries", [])
    }
    memory_entities = {e.lower() for e in memory.get("triggered_by_entities", [])}
    return bool(candidates & memory_entities)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
