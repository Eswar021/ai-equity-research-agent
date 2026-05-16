"""
intelligence_layer/evidence_builder/layer8_runner.py — Layer 8

Main controller for Evidence Builder.
Reads L5 + L6 + L7 outputs, computes features, builds evidence cards,
thesis cards, target evidence packs, and agent context packets.

Pipeline (8 steps):
  1. Load upstream inputs (L5, L6, L7)
  2. Resolve per-target evidence scopes
  3. Compute numeric features per target (price, fundamental, valuation, peer, analyst)
  4. Build evidence cards per target
  5. Score evidence strength
  6. Map evidence gaps
  7. Build thesis cards, evidence packs, agent context packets
  8. Write all artifacts + L9 manifest

Run standalone:
    python intelligence_layer/evidence_builder/layer8_runner.py
    python intelligence_layer/evidence_builder/layer8_runner.py --date 2026-05-10

ADR-L8-001: reads L7 raw JSON directly — no L2/L3 targeted pass
ADR-L8-009: 4 agent types (fundamental, valuation, risk, thesis)
"""

from __future__ import annotations
import argparse
import json
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.paths import LAYER5_DIR, LAYER6_DIR, LAYER7_DIR, LAYER8_DIR

from intelligence_layer.evidence_builder import (
    evidence_input_loader,
    target_scope_resolver,
    price_feature_engineer,
    fundamental_feature_engineer,
    valuation_feature_engineer,
    peer_feature_engineer,
    analyst_revision_feature_engineer,
    evidence_card_builder,
    evidence_strength_scorer,
    evidence_gap_mapper,
    thesis_card_builder,
    target_evidence_pack_builder,
    agent_context_packet_builder,
    evidence_quality_reporter,
)

_IST = timezone(timedelta(hours=5, minutes=30))


def run(layer5_dir: Path, layer6_dir: Path, layer7_dir: Path, layer8_dir: Path) -> dict:
    layer5_dir = Path(layer5_dir)
    layer6_dir = Path(layer6_dir)
    layer7_dir = Path(layer7_dir)
    layer8_dir = Path(layer8_dir)
    layer8_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y-%m-%d").replace("-", "")

    print(f"\n{'='*60}")
    print(f"Layer 8 — Evidence Builder")
    print(f"L5 dir: {layer5_dir}")
    print(f"L6 dir: {layer6_dir}")
    print(f"L7 dir: {layer7_dir}")
    print(f"L8 dir: {layer8_dir}")
    print(f"{'='*60}\n")

    # ── Step 1: Load inputs ────────────────────────────────────────────────────
    print("[1/8] Loading upstream inputs...")
    inputs = evidence_input_loader.load(layer5_dir, layer6_dir, layer7_dir)
    research_run_id = inputs.get("research_run_id", f"RUN_{today}")
    targets = inputs["selected_targets"]
    print(f"       selected_targets={len(targets)} hypotheses={len(inputs['opportunity_hypotheses'])} warnings={len(inputs['load_warnings'])}")
    for w in inputs["load_warnings"]:
        print(f"       WARN: {w}")

    # ── Step 2: Resolve scopes ─────────────────────────────────────────────────
    print("[2/8] Resolving target evidence scopes...")
    scopes = target_scope_resolver.resolve_all_scopes(
        inputs["selected_targets"],
        inputs["hyp_by_id"],
        inputs["coverage_by_target"],
        inputs["missing_by_target"],
        inputs["target_files"],
        inputs["market_view"],
    )
    print(f"       {len(scopes)} scopes resolved")
    for s in scopes:
        print(f"       {s['target_id']} | {s['target_name'][:35]:35} | modules={len(s['available_modules'])}")

    # ── Per-target processing ──────────────────────────────────────────────────
    all_feature_groups: dict[str, list[dict]] = {}
    all_evidence:       dict[str, list[dict]] = {}
    all_gaps:           dict[str, list[dict]] = {}
    all_thesis_cards:   list[dict]  = []
    all_packs:          list[dict]  = []
    all_packets:        list[dict]  = []

    # Step 3 + 4 + 5 + 6 + 7 per target
    print("[3-7/8] Processing targets...")
    for scope in scopes:
        tid  = scope["target_id"]
        name = scope["target_name"]
        print(f"\n  [{tid}] {name} ({scope['ticker']})")

        # Step 3: Feature engineering
        price_feats  = price_feature_engineer.compute(scope)
        fund_feats   = fundamental_feature_engineer.compute(scope)
        peer_feats   = peer_feature_engineer.compute(scope)
        analyst_feats = analyst_revision_feature_engineer.compute(scope)
        val_feats    = valuation_feature_engineer.compute(scope, price_feats, fund_feats, peer_feats)

        feature_groups = [price_feats, fund_feats, val_feats, peer_feats, analyst_feats]
        all_feature_groups[tid] = feature_groups

        for fg in feature_groups:
            q = fg["data_quality"]
            print(f"    feature: {fg['feature_group_id']}  completeness={q['completeness_score']:.2f}"
                  + (f"  WARN: {q['warnings'][0]}" if q.get("warnings") else ""))

        # Step 4: Evidence cards
        cards = evidence_card_builder.build_all_cards(
            scope, price_feats, fund_feats, val_feats, peer_feats, analyst_feats,
            date_str=today,
        )
        print(f"    evidence_cards={len(cards)}")

        # Step 5: Score
        cards = evidence_strength_scorer.score_all(cards)

        # Step 6: Gaps
        gaps = evidence_gap_mapper.map_gaps(scope, date_str=today)
        print(f"    evidence_gaps={len(gaps)}")

        all_evidence[tid] = cards
        all_gaps[tid]     = gaps

        # Step 7a: Thesis card
        thesis = thesis_card_builder.build(scope, cards, gaps, date_str=today)
        all_thesis_cards.append(thesis)
        print(f"    thesis_confidence={thesis['current_thesis_confidence']:.2f}")

        # Step 7b: Evidence pack
        pack = target_evidence_pack_builder.build(scope, feature_groups, cards, thesis, gaps, date_str=today)
        all_packs.append(pack)

        # Step 7c: Agent context packets
        packets = agent_context_packet_builder.build_all(
            scope, feature_groups, cards, thesis, gaps, pack, date_str=today
        )
        all_packets.extend(packets)
        print(f"    agent_packets={len(packets)}")

    # ── Step 8: Write all artifacts ────────────────────────────────────────────
    print("\n[8/8] Writing artifacts...")

    # Flatten structures for file output
    all_features_flat = [fg for fgs in all_feature_groups.values() for fg in fgs]
    all_cards_flat    = [c for cards in all_evidence.values() for c in cards]
    all_gaps_flat     = [g for gaps in all_gaps.values() for g in gaps]

    _write(layer8_dir / "numeric_features.json",       all_features_flat)
    _write(layer8_dir / "evidence_cards.json",          all_cards_flat)
    _write(layer8_dir / "evidence_gap_report.json",     all_gaps_flat)
    _write(layer8_dir / "thesis_cards.json",            all_thesis_cards)
    _write(layer8_dir / "target_evidence_packs.json",   all_packs)
    _write(layer8_dir / "agent_context_packets.json",   all_packets)

    # Quality report
    quality_report = evidence_quality_reporter.build_report(
        research_run_id=research_run_id,
        scopes=scopes,
        all_evidence=all_evidence,
        all_gaps=all_gaps,
        all_packs=all_packs,
        all_packets=all_packets,
        date_str=today,
    )
    _write(layer8_dir / "evidence_quality_report.json", quality_report)

    # Manifest
    manifest = {
        "research_run_id":   research_run_id,
        "layer":             "L8_evidence_builder",
        "created_at":        datetime.now(_IST).isoformat(),
        "targets_processed": len(scopes),
        "artifacts": {
            "numeric_features":      str(layer8_dir / "numeric_features.json"),
            "evidence_cards":        str(layer8_dir / "evidence_cards.json"),
            "evidence_gap_report":   str(layer8_dir / "evidence_gap_report.json"),
            "thesis_cards":          str(layer8_dir / "thesis_cards.json"),
            "target_evidence_packs": str(layer8_dir / "target_evidence_packs.json"),
            "agent_context_packets": str(layer8_dir / "agent_context_packets.json"),
            "evidence_quality_report": str(layer8_dir / "evidence_quality_report.json"),
        },
        "counts": {
            "feature_groups":     len(all_features_flat),
            "evidence_cards":     len(all_cards_flat),
            "evidence_gaps":      len(all_gaps_flat),
            "thesis_cards":       len(all_thesis_cards),
            "target_packs":       len(all_packs),
            "agent_packets":      len(all_packets),
        },
        "next_layer_input": {
            "target_evidence_packs_path": str(layer8_dir / "target_evidence_packs.json"),
            "agent_context_packets_path": str(layer8_dir / "agent_context_packets.json"),
            "evidence_cards_path":        str(layer8_dir / "evidence_cards.json"),
            "numeric_features_path":      str(layer8_dir / "numeric_features.json"),
            "thesis_cards_path":          str(layer8_dir / "thesis_cards.json"),
            "evidence_gap_report_path":   str(layer8_dir / "evidence_gap_report.json"),
            "evidence_quality_report_path": str(layer8_dir / "evidence_quality_report.json"),
        },
    }
    _write(layer8_dir / "layer8_manifest.json", manifest)

    qr = quality_report
    print(f"\n{'='*60}")
    print(f"Layer 8 complete.")
    print(f"  Targets processed    : {qr['targets_processed']}")
    print(f"  Targets ready        : {qr['targets_ready_for_agents']}")
    print(f"  Evidence cards       : {qr['evidence_cards_created']}")
    print(f"  Evidence gaps        : {qr['evidence_gaps_count']}")
    print(f"  Critical gaps        : {qr['critical_gaps_count']}")
    print(f"  Agent packets        : {qr['agent_context_packets']}")
    print(f"  Avg evidence strength: {qr['average_evidence_strength']}")
    print(f"  Strength breakdown   : {qr['evidence_strength_distribution']}")
    print(f"  Output dir           : {layer8_dir}")
    print(f"{'='*60}\n")

    return manifest


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"       wrote {path.name}  ({len(data) if isinstance(data, list) else 'obj'} items)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 8 — Evidence Builder")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"),
                        help="Target date (YYYY-MM-DD). Defaults to today.")
    args = parser.parse_args()

    target_date = args.date
    base_out   = Path(__file__).parent.parent.parent / "output" / target_date
    layer5_dir = base_out / "layer5"
    layer6_dir = base_out / "layer6"
    layer7_dir = base_out / "layer7"
    layer8_dir = base_out / "layer8"

    if not (layer6_dir / "selected_research_targets.json").exists():
        print(f"ERROR: selected_research_targets.json not found at {layer6_dir}", file=sys.stderr)
        sys.exit(1)

    if not layer7_dir.exists():
        print(f"ERROR: Layer 7 output not found at {layer7_dir}", file=sys.stderr)
        sys.exit(1)

    run(layer5_dir, layer6_dir, layer7_dir, layer8_dir)


if __name__ == "__main__":
    main()
