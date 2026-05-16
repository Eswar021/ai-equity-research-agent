"""
L4 Memory Qualification — recalls past memory context and scores new candidates.

Reads:
    output/{date}/run_manifest.json          → layer_4 config
    output/{date}/L3/enriched_records.json   → enriched records (L3 output)
    db/memory/entity_memory_index.json       → entity name → [memory_id] lookup
    db/memory/theme_memory_index.json        → theme name  → [memory_id] lookup
    db/memory/*.jsonl                        → actual memory records (for recall)

Writes:
    output/{date}/L4/memory_context.json     → records + memory_candidates + recalled memory
    output/{date}/L4/summary.json            → recall + scoring stats

LLM: no — entirely rule-based

Module execution order:
    1. Load manifest → layer_4 config
    2. Load L3/enriched_records.json
    3. Load entity/theme memory indexes (empty on first clean-slate run)
    4. Load all db/memory/ JSONL files → {memory_id: record} lookup dict
    5. RECALL: collect all entities+themes across records → index lookup → memory records
    6. SCORE: per record → per event + market_signal → 3-factor score → memory_candidate
    7. Write L4/memory_context.json + summary.json

Note: L4 does NOT write to db/memory/. Memory writes happen at L10 after the full
pipeline has processed everything — better quality decisions with full context available.

Usage:
    python -m src.pipeline.L4_memory.runner              # today
    python -m src.pipeline.L4_memory.runner --date 2026-05-17
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, PROJECT_ROOT, load_manifest, output_dir, today

_DB_MEMORY    = PROJECT_ROOT / "db" / "memory"
_ENTITY_INDEX = _DB_MEMORY / "entity_memory_index.json"
_THEME_INDEX  = _DB_MEMORY / "theme_memory_index.json"
_JSONL_FILES  = [
    "watch_memory.jsonl",
    "short_term_market_memory.jsonl",
    "long_term_investment_memory.jsonl",
    "thesis_memory.jsonl",
]


# ---------------------------------------------------------------------------
# Memory loading helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    return records


def _load_memory_lookup() -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for fname in _JSONL_FILES:
        for rec in _load_jsonl(_DB_MEMORY / fname):
            mid = rec.get("memory_id")
            if mid:
                lookup[mid] = rec
    return lookup


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _novelty_score(entity: str, entity_index: dict) -> int:
    if not entity:
        return 10
    return 15 if entity.lower() in entity_index else 40


def _recency_score(published_at: str | None) -> int:
    if not published_at:
        return 5
    try:
        dt = datetime.fromisoformat(published_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        age_days = (datetime.now(IST) - dt).days
        if age_days <= 0:
            return 20
        elif age_days == 1:
            return 15
        elif age_days <= 3:
            return 10
        else:
            return 5
    except Exception:
        return 5


def _importance_event(event: dict, extraction_confidence: str) -> int:
    score = 0
    etype = event.get("event_type", "")
    if etype in ("earnings", "merger"):
        score += 20
    elif etype == "regulatory":
        score += 15
    else:
        score += 5
    if extraction_confidence == "high":
        score += 10
    elif extraction_confidence == "medium":
        score += 5
    return min(score, 40)


def _importance_signal(signal: dict, extraction_confidence: str) -> int:
    score = 0
    direction  = signal.get("direction", "neutral")
    confidence = signal.get("confidence", "low")
    if direction in ("bullish", "bearish"):
        if confidence == "high":
            score += 20
        elif confidence == "medium":
            score += 12
        else:
            score += 5
    if extraction_confidence == "high":
        score += 10
    elif extraction_confidence == "medium":
        score += 5
    return min(score, 40)


def _recommended_type(total_score: int, event_type: str, watch_types: set) -> str | None:
    if event_type in watch_types:
        return "watch_memory"
    if total_score >= 65:
        return "long_term_investment_memory"
    if total_score >= 40:
        return "short_term_market_memory"
    return None


def _make_source_ref(rec: dict) -> dict:
    return {
        "record_id":         rec["id"],
        "source":            rec.get("source", ""),
        "source_type":       rec.get("source_type", ""),
        "supporting_text":   (rec.get("content") or "")[:300],
        "published_at":      rec.get("published_at"),
        "source_reliability": rec.get("source_reliability", ""),
    }


def _score_record(rec: dict, entity_index: dict, cfg: dict) -> list[dict]:
    watch_types = set(cfg.get("watch_event_types", []))
    threshold   = int(cfg.get("worth_storing_threshold", 40))
    ext_conf    = rec.get("extraction_confidence", "")
    source_ref  = _make_source_ref(rec)
    candidates  = []

    for event in rec.get("events", []):
        entity     = event.get("entity", "")
        etype      = event.get("event_type", "")
        novelty    = _novelty_score(entity, entity_index)
        importance = _importance_event(event, ext_conf)
        recency    = _recency_score(rec.get("published_at"))
        total      = novelty + importance + recency
        worth      = total >= threshold or etype in watch_types
        candidates.append({
            "object_type":             "event",
            "title":                   event.get("text", "")[:120],
            "entity":                  entity,
            "event_type":              etype,
            "direction":               event.get("direction", ""),
            "novelty_score":           novelty,
            "importance_score":        importance,
            "recency_score":           recency,
            "total_score":             total,
            "confidence":              round(total / 100, 2),
            "worth_storing":           worth,
            "recommended_memory_type": _recommended_type(total, etype, watch_types),
            "source_ref":              source_ref,
        })

    for signal in rec.get("market_signals", []):
        entity     = signal.get("entity", "")
        novelty    = _novelty_score(entity, entity_index)
        importance = _importance_signal(signal, ext_conf)
        recency    = _recency_score(rec.get("published_at"))
        total      = novelty + importance + recency
        worth      = total >= threshold
        candidates.append({
            "object_type":             "market_signal",
            "title":                   signal.get("text", "")[:120],
            "entity":                  entity,
            "direction":               signal.get("direction", ""),
            "signal_confidence":       signal.get("confidence", ""),
            "novelty_score":           novelty,
            "importance_score":        importance,
            "recency_score":           recency,
            "total_score":             total,
            "confidence":              round(total / 100, 2),
            "worth_storing":           worth,
            "recommended_memory_type": _recommended_type(total, "", watch_types),
            "source_ref":              source_ref,
        })

    return candidates


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(run_date: str | None = None) -> Path:
    date     = run_date or today()
    manifest = load_manifest(date)
    l4_cfg   = manifest.get("layer_4")
    if not l4_cfg:
        raise KeyError(f"run_manifest.json for {date} has no 'layer_4' key — re-run L0 first")

    l3_path = output_dir(date) / "L3" / "enriched_records.json"
    if not l3_path.exists():
        raise FileNotFoundError(f"L3 output not found: {l3_path} — run L3 first")

    l3_data = json.loads(l3_path.read_text())
    records: list[dict] = l3_data.get("records", [])

    entity_index: dict = json.loads(_ENTITY_INDEX.read_text()) if _ENTITY_INDEX.exists() else {}
    theme_index:  dict = json.loads(_THEME_INDEX.read_text())  if _THEME_INDEX.exists()  else {}
    memory_lookup = _load_memory_lookup()

    max_per = int(l4_cfg.get("max_recall_per_entity", 5))

    # RECALL — collect all entities + themes from all records, lookup in indexes
    all_entities: set[str] = set()
    all_themes:   set[str] = set()
    for rec in records:
        for e in rec.get("entities", []):
            name = e.get("name", "")
            if name:
                all_entities.add(name.lower())
        for t in rec.get("themes", []):
            if t:
                all_themes.add(t.lower())

    recalled_memory: list[dict] = []
    seen_mem: set[str] = set()

    for ent in sorted(all_entities):
        mids = entity_index.get(ent, [])[:max_per]
        for mid in mids:
            if mid in memory_lookup and mid not in seen_mem:
                seen_mem.add(mid)
                recalled_memory.append({
                    **memory_lookup[mid],
                    "triggered_by_entities":   [ent],
                    "triggered_by_record_ids": [],
                })

    for theme in sorted(all_themes):
        mids = theme_index.get(theme, [])[:max_per]
        for mid in mids:
            if mid in memory_lookup and mid not in seen_mem:
                seen_mem.add(mid)
                recalled_memory.append({
                    **memory_lookup[mid],
                    "triggered_by_themes":     [theme],
                    "triggered_by_record_ids": [],
                })

    # SCORE — attach memory_candidates to each record
    total_candidates    = 0
    total_worth_storing = 0
    for rec in records:
        candidates = _score_record(rec, entity_index, l4_cfg)
        rec["memory_candidates"] = candidates
        total_candidates    += len(candidates)
        total_worth_storing += sum(1 for c in candidates if c["worth_storing"])

    print(f"  L4: {len(records)} records — entities={len(all_entities)}, themes={len(all_themes)}")
    print(f"  Recalled: {len(recalled_memory)} past memories")
    print(f"  Candidates: {total_candidates} scored, {total_worth_storing} worth_storing")

    out_dir  = output_dir(date) / "L4"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "memory_context.json"
    out_path.write_text(json.dumps({
        "run_date":      date,
        "run_id":        l3_data.get("run_id", ""),
        "total_records": len(records),
        "total_memory":  len(recalled_memory),
        "records":       records,
        "memory":        recalled_memory,
    }, indent=2, ensure_ascii=False))

    (out_dir / "summary.json").write_text(json.dumps({
        "date":              date,
        "total_records":     len(records),
        "entities_queried":  len(all_entities),
        "themes_queried":    len(all_themes),
        "total_recalled":    len(recalled_memory),
        "total_candidates":  total_candidates,
        "worth_storing":     total_worth_storing,
        "skipped_low_score": total_candidates - total_worth_storing,
    }, indent=2))

    print(f"\n  L4 done: {len(records)} records enriched, {len(recalled_memory)} recalled")
    print(f"  → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Run date YYYY-MM-DD (default: today)")
    args = parser.parse_args()
    run(args.date)
