"""
Two-pass news matching: joins L4 enriched records to each deep-dive target.

Pass 1 — hypothesis_source:
    Pull records by record_ids from the L6 target (the exact articles that
    generated the hypothesis). Always included; tagged as "hypothesis_source".

Pass 2 — entity_match:
    Scan remaining L4 records for entity name overlap with the target entity,
    beneficiary names, and resolved tickers. Ranked by overlap score + signal count;
    top N taken up to (max_supporting_news - pass1_count). Tagged as "entity_match".

Full article content is NOT included — only signal extracts, key facts, key events.
This keeps packets lean while giving L9 agents the highest-value evidence.
"""

from __future__ import annotations


def _candidate_names(target: dict, bundle: dict) -> set[str]:
    """Lowercase name set: target entity + beneficiaries + resolved tickers."""
    names: set[str] = set()
    entity = target.get("target_entity", "").lower().strip()
    if entity:
        names.add(entity)
    for b in target.get("beneficiaries", []):
        names.add(b.lower().strip())
    for t in bundle.get("resolved_tickers", []):
        names.add(t.lower().strip())
    names.discard("")
    return names


def _overlap_score(record: dict, candidates: set[str]) -> int:
    """Score = (entity name matches × 2) + market signal count."""
    entity_names = {e.get("name", "").lower().strip() for e in record.get("entities", [])}
    hits = sum(
        1 for name in entity_names
        if any(c in name or name in c for c in candidates)
    )
    return hits * 2 + len(record.get("market_signals", []))


def _slim(record: dict, relevance_type: str, max_facts: int, max_events: int) -> dict:
    """Extract what L9 agents need — analysis summary + structured extracts, no raw content.

    analysis: L3's investment-relevant summary of the article — the reasoning behind signals.
    themes: investment context framing (rate cut, NIM expansion, asset quality, etc.)
    Full article content is excluded — analysis already distilled it, and raw text
    bloats the prompt without adding value over the structured extractions.
    """
    return {
        "record_id":          record.get("id", ""),
        "source":             record.get("source", ""),
        "source_reliability": record.get("source_reliability", ""),
        "title":              record.get("title"),
        "published_at":       record.get("published_at"),
        "relevance_type":     relevance_type,
        "analysis":           record.get("analysis", ""),
        "themes":             record.get("themes", []),
        "market_signals":     record.get("market_signals", []),
        "key_facts":          record.get("facts", [])[:max_facts],
        "key_events":         record.get("events", [])[:max_events],
    }


def match(
    target: dict,
    bundle: dict,
    record_index: dict[str, dict],
    all_records: list[dict],
    cfg: dict,
) -> list[dict]:
    """
    Returns supporting_news list for one target.
    record_index: {record_id: record} built from all L4 records.
    all_records: flat L4 records list (used for entity_match scan).
    """
    max_news  = cfg.get("max_supporting_news", 15)
    max_facts = cfg.get("max_facts_per_record", 3)
    max_evts  = cfg.get("max_events_per_record", 3)
    min_score = cfg.get("min_entity_match_score", 2)

    result: list[dict] = []
    seen:   set[str]   = set()

    # Pass 1 — hypothesis_source: exact record_ids from the L6 target
    for rid in target.get("record_ids", []):
        rec = record_index.get(rid)
        if rec:
            result.append(_slim(rec, "hypothesis_source", max_facts, max_evts))
            seen.add(rid)

    # Pass 2 — entity_match: scan remaining records for name overlap
    remaining = max_news - len(result)
    candidates = _candidate_names(target, bundle)

    if remaining > 0 and candidates:
        scored: list[tuple[int, dict]] = []
        for rec in all_records:
            rid = rec.get("id", "")
            if rid in seen:
                continue
            score = _overlap_score(rec, candidates)
            if score >= min_score:
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        for _, rec in scored[:remaining]:
            result.append(_slim(rec, "entity_match", max_facts, max_evts))

    return result
