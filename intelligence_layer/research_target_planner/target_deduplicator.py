"""
intelligence_layer/research_target_planner/target_deduplicator.py — Layer 6

Merges duplicate/overlapping target candidates.
The same company (e.g. "HDFC Bank", "HDFC Bank Ltd", "HDFCBANK.NS") can appear
across many hypotheses. This collapses them into one enriched target.

Merge keys (in priority order):
  1. Normalized ticker (e.g. HDFCBANK.NS)
  2. Normalized entity name (strip Ltd/Limited/Corp, lowercase)

Design doc: docs/system_design_docs/layer_6.md §13 target_deduplicator.py
"""

from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_STRIP_RE = re.compile(
    r'\s*(ltd\.?|limited|corp\.?|corporation|inc\.?|pvt\.?|private|'
    r'\(india\)|india|technologies|technology|solutions|services|group|'
    r'limited\.|holdings|enterprises)\s*$',
    re.IGNORECASE
)


def deduplicate(candidates: list[dict]) -> list[dict]:
    """
    Merge candidates by ticker (primary) or normalized name (secondary).
    Returns a flat list of merged target dicts.
    """
    today = datetime.now(_IST).strftime("%Y%m%d")

    # Group by merge key
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        key = _merge_key(c)
        groups.setdefault(key, []).append(c)

    merged: list[dict] = []
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(_to_target(group[0], today))
        else:
            merged.append(_merge_group(group, today))

    return merged


def _merge_key(c: dict) -> str:
    ticker = (c.get("ticker") or "").upper().strip()
    if ticker:
        return f"TICKER:{ticker}"
    name = _normalize(c.get("candidate_name") or c.get("resolved_entity_name") or "")
    if name:
        return f"NAME:{name}"
    # fallback: keep separate
    return f"ID:{c.get('candidate_target_id', id(c))}"


def _normalize(name: str) -> str:
    n = name.lower().strip()
    n = _STRIP_RE.sub("", n).strip()
    n = re.sub(r'\s+', ' ', n)
    return n


def _to_target(c: dict, today: str) -> dict:
    _CTR[0] += 1
    return {
        "target_id":              f"TARGET_{today}_{_CTR[0]:04d}",
        "target_name":            c.get("resolved_entity_name") or c.get("candidate_name", ""),
        "target_type":            c.get("target_type", "unknown"),
        "ticker":                 c.get("ticker"),
        "exchange":               c.get("exchange"),
        "market":                 c.get("market", "india"),
        "time_horizon":           c.get("time_horizon", "medium_term"),
        "source_opportunity_ids": [c.get("source_opportunity_id", "")],
        "merged_from":            [c.get("candidate_target_id", "")],
        "why_selected":           c.get("why_candidate", []),
        "questions_to_answer":    c.get("questions_to_answer", []),
        "supporting_refs":        c.get("supporting_refs", []),
        "data_gaps":              c.get("data_gaps", []),
        "confidence":             c.get("confidence", 0.5),
        "entity_id":              c.get("entity_id"),
        "resolution_status":      c.get("resolution_status", ""),
        "ticker_resolution_status": c.get("ticker_resolution_status", ""),
        "classification_confidence": c.get("classification_confidence", 0.5),
    }


def _merge_group(group: list[dict], today: str) -> dict:
    _CTR[0] += 1
    # Representative = highest confidence in group
    rep = max(group, key=lambda c: c.get("confidence", 0))

    # Collect combined data
    opp_ids = list(dict.fromkeys(
        c.get("source_opportunity_id", "") for c in group if c.get("source_opportunity_id")
    ))
    cand_ids = [c.get("candidate_target_id", "") for c in group]
    why      = []
    for c in group:
        why.extend(c.get("why_candidate") or [])
    why = list(dict.fromkeys(why))[:6]

    questions: list[str] = []
    for c in group:
        questions.extend(c.get("questions_to_answer") or [])
    questions = list(dict.fromkeys(questions))[:5]

    refs: list[str] = []
    for c in group:
        refs.extend(c.get("supporting_refs") or [])
    refs = list(dict.fromkeys(refs))[:8]

    gaps: list[str] = []
    for c in group:
        gaps.extend(c.get("data_gaps") or [])
    gaps = list(dict.fromkeys(gaps))[:5]

    conf = max(c.get("confidence", 0) for c in group)

    # Pick best ticker
    ticker = rep.get("ticker")
    for c in group:
        if c.get("ticker"):
            ticker = c["ticker"]
            break

    return {
        "target_id":              f"TARGET_{today}_{_CTR[0]:04d}",
        "target_name":            rep.get("resolved_entity_name") or rep.get("candidate_name", ""),
        "target_type":            rep.get("target_type", "unknown"),
        "ticker":                 ticker,
        "exchange":               rep.get("exchange"),
        "market":                 rep.get("market", "india"),
        "time_horizon":           rep.get("time_horizon", "medium_term"),
        "source_opportunity_ids": opp_ids,
        "merged_from":            cand_ids,
        "why_selected":           why,
        "questions_to_answer":    questions,
        "supporting_refs":        refs,
        "data_gaps":              gaps,
        "confidence":             round(conf, 3),
        "entity_id":              rep.get("entity_id"),
        "resolution_status":      rep.get("resolution_status", ""),
        "ticker_resolution_status": rep.get("ticker_resolution_status", ""),
        "classification_confidence": rep.get("classification_confidence", 0.5),
        "merged_count":           len(group),
    }


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from intelligence_layer.research_target_planner import (
        planning_input_loader, opportunity_filter, target_candidate_builder,
        target_type_classifier, entity_resolver, ticker_resolver,
        unresolved_entity_preserver)

    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-10"
    base = Path(__file__).parent.parent.parent / "output" / date
    ctx  = planning_input_loader.load(base / "layer3", base / "layer4", base / "layer5")
    filt = opportunity_filter.filter_opportunities(ctx["opportunity_hypotheses"])
    cands = target_candidate_builder.build_candidates(filt["accepted"])
    cands = target_type_classifier.classify_all(cands)
    cands = entity_resolver.resolve_all(cands, ctx["entity_by_ticker"], ctx["entity_by_norm"])
    cands = ticker_resolver.resolve_all(cands)
    resolved, unresolved = unresolved_entity_preserver.preserve_unresolved(cands)

    deduped = deduplicate(resolved)
    print(f"Raw resolved candidates : {len(resolved)}")
    print(f"After dedup             : {len(deduped)}")
    print()
    merged_multi = [t for t in deduped if t.get("merged_count", 1) > 1]
    print(f"Targets merged from >1 source: {len(merged_multi)}")
    for t in sorted(merged_multi, key=lambda x: x.get("merged_count", 0), reverse=True)[:5]:
        print(f"  [{t['target_id']}] {t['target_name'][:40]} ← {t['merged_count']} candidates  ticker={t['ticker']}")
